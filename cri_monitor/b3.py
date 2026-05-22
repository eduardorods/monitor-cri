import base64
import datetime
import json
import sys
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
FNET_BASE_URL = "https://fnet.bmfbovespa.com.br/fnet/publico/"
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

    def _buscar_id_fundo_fnet(self, isin: str) -> Optional[int]:
        """Resolve ISIN → idFundo interno do FNet (sistema CVM de certificados)."""
        try:
            resp = self.session.get(
                FNET_BASE_URL + "listarFundos",
                params={"term": isin, "page": 1, "idTipoFundo": 0,
                        "idAdm": 0, "paraCerts": "true"},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            items = data if isinstance(data, list) else data.get("results", [])
            if items:
                return items[0].get("id")
        except Exception:
            pass
        return None

    def _documentos_fnet_cvm(self, id_fundo: int) -> Iterator[dict]:
        """Busca documentos no sistema FNet/CVM pelo idFundo, com paginação."""
        start = 0
        page_size = 100
        while True:
            params = {
                "d": 1,
                "s": start,
                "l": page_size,
                "o[0][dataEntrega]": "desc",
                "idFundo": id_fundo,
                "idCategoriaDocumento": 0,
                "idTipoDocumento": 0,
                "idEspecieDocumento": 0,
                "paginaCertificados": "true",
                "isSession": "false",
            }
            try:
                resp = self.session.get(
                    FNET_BASE_URL + "pesquisarGerenciadorDocumentosDados",
                    params=params,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                print(f"  Erro ao buscar docs FNet: {e}", file=sys.stderr)
                return
            items = data.get("data", [])
            yield from items
            total = data.get("recordsTotal", 0)
            start += page_size
            if start >= total or not items:
                return

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

        # Se CNPJ foi informado explicitamente, usa ele
        if cnpj_securitizadora and not info.cnpj_securitizadora:
            info.cnpj_securitizadora = cnpj_securitizadora

        # Tenta resolver CNPJ a partir do nome da securitizadora (balcão não retorna CNPJ)
        if not info.cnpj_securitizadora and info.nome_securitizadora:
            info.cnpj_securitizadora = encontrar_cnpj_por_nome(info.nome_securitizadora)

        if incluir_documentos:
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
        # Busca via FNet/CVM por ISIN (API correta para CRI)
        if info.isin:
            print(f"  FNet CVM: buscando idFundo para ISIN={info.isin}...", file=sys.stderr)
            id_fundo = self._buscar_id_fundo_fnet(info.isin)
            if id_fundo:
                print(f"  FNet CVM: idFundo={id_fundo}, buscando documentos...", file=sys.stderr)
                docs = [_build_documento_fnet(d) for d in self._documentos_fnet_cvm(id_fundo)]
                print(f"  FNet CVM: {len(docs)} documento(s) encontrado(s).", file=sys.stderr)
                return docs
            else:
                print(f"  FNet CVM: idFundo não encontrado para ISIN={info.isin}.", file=sys.stderr)

        # Fallback: GetListedDocumentsTypeHistory por CNPJ
        if not info.cnpj_securitizadora:
            return []
        start = _parse_date(info.data_emissao) or datetime.date(2010, 1, 1)
        end = datetime.date.today()
        print(f"  FNet fallback: CNPJ={info.cnpj_securitizadora} período={start} a {end}",
              file=sys.stderr)

        todos: list[Documento] = []
        por_codigo: list[Documento] = []
        for doc in self._documentos_por_cnpj(info.cnpj_securitizadora, start, end):
            built = _build_documento(doc)
            todos.append(built)
            if _documento_relacionado(doc, info.codigo_if, info.isin):
                por_codigo.append(built)

        if por_codigo:
            return por_codigo
        print(f"  FNet fallback: {len(todos)} doc(s) da securitizadora (sem match por código).",
              file=sys.stderr)
        return todos

    def _documentos_por_cnpj(
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


def _build_documento_fnet(doc: dict) -> Documento:
    """Constrói Documento a partir da resposta do FNet CVM (pesquisarGerenciadorDocumentosDados)."""
    doc_id = doc.get("id") or doc.get("idDocumento")
    url = None
    if doc_id:
        url = f"{FNET_BASE_URL}downloadDocumento?id={doc_id}&cvm=true"
    nome = (doc.get("descricao") or doc.get("nomeDocumento") or
            doc.get("nome") or doc.get("name"))
    tipo = (doc.get("tipoDocumento") or doc.get("tipo") or
            doc.get("typeName"))
    categoria = (doc.get("categoriaDocumento") or doc.get("categoria") or
                 doc.get("categoryName"))
    return Documento(
        nome=nome,
        tipo=tipo,
        categoria=categoria,
        categoria_normalizada=_categorizar(nome, tipo, categoria),
        data_entrega=doc.get("dataEntrega") or doc.get("submissionDate"),
        data_referencia=doc.get("dataReferencia") or doc.get("referenceDate"),
        url=url,
        raw=doc,
    )


def _build_documento(doc: dict) -> Documento:
    doc_id = doc.get("id") or doc.get("idDocumento")
    url = None
    if doc_id:
        url = f"{FNET_BASE_URL}downloadDocumento?id={doc_id}"
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


def _documento_relacionado(
    doc: dict,
    codigo_if: Optional[str],
    isin: Optional[str] = None,
) -> bool:
    if not codigo_if and not isin:
        return True
    campos_texto = " ".join(
        str(doc.get(k, "")) for k in ("name", "nome", "description", "descricao", "identificationCode")
    ).upper()
    if codigo_if and codigo_if.upper() in campos_texto:
        return True
    if isin and isin.upper() in campos_texto:
        return True
    return False


def _formatar_cnpj(cnpj: str) -> str:
    d = "".join(c for c in cnpj if c.isdigit())
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return cnpj


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
