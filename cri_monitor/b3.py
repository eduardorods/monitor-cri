import base64
import datetime
import json
from dataclasses import dataclass, field, asdict
from typing import Any, Iterator, Optional
from urllib.parse import urljoin

import requests

from cri_monitor.securitizadoras import (
    SECURITIZADORAS_CONHECIDAS,
    encontrar_cnpj_por_nome,
)


CATEGORIAS_DOCUMENTO = {
    "termo_securitizacao": ["termo de securitiza"],
    "aditamento": ["aditamento", "aditivo"],
    "ata_assembleia": ["ata", "assembleia"],
    "relatorio_agente_fiduciario": ["relatório do agente", "relatorio do agente",
                                    "relatório anual do agente", "relatório do trustee"],
}


FUNDS_CALL_URL = "https://sistemaswebb3-listados.b3.com.br/fundsProxy/fundsCall/"
BALCAO_CALL_URL = "https://sistemaswebb3-balcao.b3.com.br/featuresCRIProxy/CriCall/"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}


@dataclass
class Documento:
    nome: Optional[str] = None
    tipo: Optional[str] = None
    categoria: Optional[str] = None
    categoria_normalizada: Optional[str] = None
    data_entrega: Optional[str] = None
    data_referencia: Optional[str] = None
    url: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass
class CRIInfo:
    codigo_if: Optional[str] = None
    isin: Optional[str] = None
    nome: Optional[str] = None
    cnpj_securitizadora: Optional[str] = None
    nome_securitizadora: Optional[str] = None
    agente_fiduciario: Optional[str] = None
    emissao: Optional[str] = None
    serie: Optional[str] = None
    data_emissao: Optional[str] = None
    data_vencimento: Optional[str] = None
    remuneracao: Optional[str] = None
    devedor: Optional[str] = None
    descricao: Optional[str] = None
    fase: Optional[str] = None
    documentos: list = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["documentos"] = [asdict(d) for d in self.documentos]
        return data


class B3Client:
    def __init__(self, session: Optional[requests.Session] = None, timeout: int = 30):
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.timeout = timeout

    def _encode_params(self, params: dict) -> str:
        payload = json.dumps(params, separators=(",", ":"))
        return base64.b64encode(payload.encode("utf-8")).decode("ascii")

    def _get(self, base_url: str, endpoint: str, params: dict) -> Any:
        url = urljoin(base_url, endpoint) + self._encode_params(params)
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def _paginate(self, endpoint: str, params: Optional[dict] = None) -> Iterator[dict]:
        params = dict(params or {})
        params.setdefault("pageNumber", 1)
        params.setdefault("pageSize", 100)
        while True:
            data = self._get(FUNDS_CALL_URL, endpoint, params)
            if isinstance(data, list):
                yield from data
                return
            if isinstance(data, dict) and "results" in data:
                yield from data["results"]
                page_info = data.get("page") or {}
                total_pages = page_info.get("totalPages", 1)
                if params["pageNumber"] >= total_pages:
                    return
                params["pageNumber"] += 1
            else:
                yield data
                return

    def securitizadoras(self, usar_lista_local: bool = False) -> Iterator[dict]:
        if usar_lista_local:
            yield from SECURITIZADORAS_CONHECIDAS
            return
        yield from self._paginate("GetListedSecuritization/")

    def cris_por_securitizadora(self, cnpj: str) -> Iterator[dict]:
        yield from self._paginate(
            "GetListedCertified/",
            {"dateInitial": "", "cnpj": cnpj, "type": "CRI"},
        )

    def documentos(
        self,
        cnpj_securitizadora: str,
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> Iterator[dict]:
        yield from self._paginate(
            "GetListedDocumentsTypeHistory/",
            {
                "cnpj": cnpj_securitizadora,
                "dateInitial": start_date.strftime("%Y-%m-%d"),
                "dateFinal": end_date.strftime("%Y-%m-%d"),
            },
        )

    def buscar_cri_balcao(self, codigo_if: str) -> Optional["CRIInfo"]:
        """Busca direta pelo código IF no sistema de balcão da B3 (retorna remuneração e vencimento)."""
        params = {
            "language": "pt-br",
            "isinCodeIF": codigo_if,
            "indexer": "",
            "pageNumber": 1,
            "pageSize": 20,
        }
        try:
            data = self._get(BALCAO_CALL_URL, "GetInitialFilter/", params)
        except Exception:
            return None
        results = data.get("results") if isinstance(data, dict) else None
        if not results:
            return None
        return _build_cri_info_balcao(results[0])

    def buscar_cri(
        self,
        codigo_if: str,
        cnpj_securitizadora: Optional[str] = None,
        incluir_documentos: bool = True,
        on_progress=None,
    ) -> Optional[CRIInfo]:
        codigo_if = codigo_if.strip().upper()

        # Tenta balcão primeiro (busca direta, retorna remuneração e vencimento)
        info = self.buscar_cri_balcao(codigo_if)

        if info is None:
            # Fallback: busca pelo sistema listados varrendo securitizadoras
            info = self._buscar_via_listados(codigo_if, cnpj_securitizadora, on_progress)

        if info is None:
            return None

        # Se CNPJ foi informado explicitamente, usa ele (necessário para documentos)
        if cnpj_securitizadora and not info.cnpj_securitizadora:
            info.cnpj_securitizadora = cnpj_securitizadora

        # Tenta resolver CNPJ a partir do nome da securitizadora (balcão não retorna CNPJ)
        if not info.cnpj_securitizadora and info.nome_securitizadora:
            info.cnpj_securitizadora = encontrar_cnpj_por_nome(info.nome_securitizadora)

        if incluir_documentos and info.cnpj_securitizadora:
            info.documentos = self._buscar_documentos_do_cri(info)

        return info

    def _buscar_via_listados(
        self,
        codigo_if: str,
        cnpj_securitizadora: Optional[str],
        on_progress=None,
    ) -> Optional[CRIInfo]:
        if cnpj_securitizadora:
            securitizadoras = [{"cnpj": cnpj_securitizadora, "companyName": None}]
        else:
            securitizadoras = _merge_securitizadoras(
                list(self.securitizadoras()),
                SECURITIZADORAS_CONHECIDAS,
            )

        for idx, sec in enumerate(securitizadoras, 1):
            cnpj = sec.get("cnpj") or sec.get("cnpjFormatado")
            if not cnpj:
                continue
            if on_progress:
                on_progress(idx, len(securitizadoras),
                            sec.get("companyName") or cnpj)
            for cri in self.cris_por_securitizadora(cnpj):
                if _match_codigo_if(cri, codigo_if):
                    return _build_cri_info(cri, sec)
        return None

    def _buscar_documentos_do_cri(self, info: CRIInfo) -> list:
        if not info.cnpj_securitizadora:
            return []
        start = _parse_date(info.data_emissao) or datetime.date(2010, 1, 1)
        end = datetime.date.today()
        resultado = []
        for doc in self.documentos(info.cnpj_securitizadora, start, end):
            if _documento_relacionado(doc, info.codigo_if):
                resultado.append(_build_documento(doc))
        return resultado


def _merge_securitizadoras(da_api: list[dict], conhecidas: list[dict]) -> list[dict]:
    cnpjs_vistos: set[str] = set()
    merged: list[dict] = []
    for sec in da_api:
        cnpj = (sec.get("cnpj") or "").replace(".", "").replace("/", "").replace("-", "")
        if cnpj and cnpj not in cnpjs_vistos:
            cnpjs_vistos.add(cnpj)
            merged.append(sec)
    for sec in conhecidas:
        cnpj = (sec.get("cnpj") or "").replace(".", "").replace("/", "").replace("-", "")
        if cnpj and cnpj not in cnpjs_vistos:
            cnpjs_vistos.add(cnpj)
            merged.append(sec)
    return merged


def _match_codigo_if(cri: dict, codigo_if: str) -> bool:
    candidatos = [
        cri.get("identificationCode"),
        cri.get("codigoIF"),
        cri.get("codigoif"),
    ]
    return any(c and c.strip().upper() == codigo_if for c in candidatos)


def _build_cri_info_balcao(cri: dict) -> CRIInfo:
    return CRIInfo(
        codigo_if=cri.get("codeIF"),
        isin=cri.get("isin"),
        nome_securitizadora=cri.get("issuer"),
        agente_fiduciario=cri.get("trustee"),
        emissao=str(cri.get("issueNo") or "") or None,
        serie=str(cri.get("seriesNo") or "") or None,
        remuneracao=cri.get("revenue"),
        data_vencimento=cri.get("endDate"),
        raw=cri,
    )


def _build_cri_info(cri: dict, sec: dict) -> CRIInfo:
    serials = (cri.get("serials") or "").strip(",")
    return CRIInfo(
        codigo_if=cri.get("identificationCode"),
        nome=cri.get("name"),
        cnpj_securitizadora=sec.get("cnpj") or cri.get("cnpj"),
        nome_securitizadora=sec.get("companyName"),
        emissao=str(cri.get("issueNumber") or "") or None,
        serie=serials or None,
        data_emissao=cri.get("issueDate"),
        devedor=cri.get("debtorName") or None,
        descricao=cri.get("debtorQualification") or None,
        fase=cri.get("fase") or None,
        raw=cri,
    )


def _build_documento(doc: dict) -> Documento:
    doc_id = doc.get("id") or doc.get("idDocumento")
    url = None
    if doc_id:
        url = f"https://fnet.bmfbovespa.com.br/fnet/publico/downloadDocumento?id={doc_id}"
    tipo = doc.get("typeName") or doc.get("tipoDocumento")
    nome = doc.get("name") or doc.get("nome")
    categoria = doc.get("categoryName") or doc.get("categoriaDocumento")
    return Documento(
        nome=nome,
        tipo=tipo,
        categoria=categoria,
        categoria_normalizada=_categorizar(nome, tipo, categoria),
        data_entrega=doc.get("submissionDate") or doc.get("dataEntrega"),
        data_referencia=doc.get("referenceDate") or doc.get("dataReferencia"),
        url=url,
        raw=doc,
    )


def _categorizar(*campos: Optional[str]) -> Optional[str]:
    texto = " ".join(c for c in campos if c).lower()
    if not texto:
        return None
    for chave, marcadores in CATEGORIAS_DOCUMENTO.items():
        if any(m in texto for m in marcadores):
            return chave
    return None


def _documento_relacionado(doc: dict, codigo_if: Optional[str]) -> bool:
    if not codigo_if:
        return True
    campos_texto = " ".join(
        str(doc.get(k, "")) for k in ("name", "nome", "description", "descricao", "identificationCode")
    ).upper()
    return codigo_if in campos_texto


def _parse_date(s: Optional[str]) -> Optional[datetime.date]:
    if not s:
        return None
    texto = s.split("T", 1)[0]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    return None
