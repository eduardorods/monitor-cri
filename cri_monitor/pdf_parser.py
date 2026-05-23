"""Extrai texto de PDF e aplica regex para campos do Termo de Securitização."""
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ResumoOperacao:
    devedor: Optional[str] = None
    cnpj_devedor: Optional[str] = None
    valor_total: Optional[str] = None
    data_emissao: Optional[str] = None
    data_vencimento: Optional[str] = None
    taxa_remuneracao: Optional[str] = None
    indice_atualizacao: Optional[str] = None
    lastro: Optional[str] = None
    garantias: list = field(default_factory=list)
    coordenador_lider: Optional[str] = None
    agente_fiduciario: Optional[str] = None
    # campos detalhados (preenchidos pelo Gemini)
    cronograma_descricao: Optional[str] = None
    garantias_detalhadas: Optional[str] = None
    covenants: list = field(default_factory=list)
    tabela_cronograma: list = field(default_factory=list)
    serie_unica: Optional[bool] = None
    series: list = field(default_factory=list)


def extrair_texto(caminho_pdf: str, max_paginas: int = 150) -> str:
    """Extrai texto de um PDF. Lê até `max_paginas` páginas.
    Usa pdfplumber (melhor para layout/colunas/tabelas) com fallback para pypdf."""
    try:
        import pdfplumber
        textos = []
        with pdfplumber.open(caminho_pdf) as pdf:
            for i, pagina in enumerate(pdf.pages):
                if i >= max_paginas:
                    break
                try:
                    txt = pagina.extract_text() or ""
                except Exception:
                    txt = ""
                textos.append(txt)
        return "\n".join(textos)
    except Exception:
        pass

    try:
        from pypdf import PdfReader
    except ImportError:
        from PyPDF2 import PdfReader  # type: ignore

    reader = PdfReader(caminho_pdf)
    textos = []
    for i, pagina in enumerate(reader.pages):
        if i >= max_paginas:
            break
        try:
            textos.append(pagina.extract_text() or "")
        except Exception:
            continue
    return "\n".join(textos)


_CNPJ_RE = re.compile(r"\b(\d{2}[.\s]?\d{3}[.\s]?\d{3}/?\d{4}-?\d{2})\b")
_DATA_RE = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")
_VALOR_RE = re.compile(
    r"R\$\s*([\d.]+(?:,\d{2})?)|\b(\d{1,3}(?:\.\d{3})+(?:,\d{2})?)\b"
)
_DEVEDOR_RE = re.compile(
    r"(?i)devedora?\s*[:\-]?\s*([A-ZÁÊÔÃÇ][A-ZÁÉÍÓÚÊÔÃÕÇ \.\-/&]{8,120})"
)
_INDICE_RE = re.compile(
    r"(?i)(IPCA|IGP[-\s]?M|CDI|TR|IGPM|SELIC|INPC)\s*\+?\s*"
    r"(\d{1,2}[.,]\d{1,5}\s*%)?"
)


def _proxima_dataset(texto: str, marcadores: list[str], janela: int = 400) -> Optional[str]:
    """Retorna o trecho de texto logo após o primeiro marcador encontrado."""
    low = texto.lower()
    for m in marcadores:
        idx = low.find(m.lower())
        if idx != -1:
            return texto[idx: idx + janela]
    return None


def analisar(texto: str) -> ResumoOperacao:
    r = ResumoOperacao()
    if not texto:
        return r

    # Devedor (primeira ocorrência razoável)
    m = _DEVEDOR_RE.search(texto)
    if m:
        cand = m.group(1).strip()
        cand = re.split(r"\b(?:CNPJ|inscrita|com sede)\b", cand, flags=re.IGNORECASE)[0]
        r.devedor = cand.strip(" .,-")

    # CNPJ do devedor (próximo à palavra "devedor")
    bloco_dev = _proxima_dataset(texto, ["Devedora:", "Devedor:", "DEVEDORA", "DEVEDOR"], 500)
    if bloco_dev:
        c = _CNPJ_RE.search(bloco_dev)
        if c:
            r.cnpj_devedor = c.group(1)

    # Data de emissão
    bloco = _proxima_dataset(texto, ["Data de Emissão", "Data da Emissão"], 200)
    if bloco:
        d = _DATA_RE.search(bloco)
        if d:
            r.data_emissao = d.group(1)

    # Data de vencimento
    bloco = _proxima_dataset(texto, ["Data de Vencimento", "Data do Vencimento"], 200)
    if bloco:
        d = _DATA_RE.search(bloco)
        if d:
            r.data_vencimento = d.group(1)

    # Valor total
    bloco = _proxima_dataset(texto, ["Valor Total da Emissão", "Valor da Emissão",
                                     "Valor Total dos CRI"], 200)
    if bloco:
        v = _VALOR_RE.search(bloco)
        if v:
            r.valor_total = "R$ " + (v.group(1) or v.group(2))

    # Taxa / índice
    bloco = _proxima_dataset(texto, ["Remuneração", "Taxa de Juros", "Atualização Monetária"], 400)
    if bloco:
        i = _INDICE_RE.search(bloco)
        if i:
            r.indice_atualizacao = i.group(1)
            r.taxa_remuneracao = (i.group(0) or "").strip()

    # Lastro
    bloco = _proxima_dataset(texto, ["Lastro:", "Créditos Imobiliários", "Créditos Originários"], 600)
    if bloco:
        r.lastro = _resumir_paragrafo(bloco)

    # Garantias (lista de marcadores comuns)
    for marcador in ["Alienação Fiduciária", "Cessão Fiduciária",
                     "Fiança", "Aval", "Coobrigação", "Fundo de Reserva",
                     "Fundo de Liquidez", "Cessão Fiduciária de Direitos"]:
        if re.search(marcador, texto, re.IGNORECASE):
            r.garantias.append(marcador)

    # Coordenador líder
    bloco = _proxima_dataset(texto, ["Coordenador Líder", "Coordenador-Líder"], 200)
    if bloco:
        partes = re.split(r"[:\n]", bloco, maxsplit=2)
        if len(partes) > 1:
            cand = partes[1].strip().split("\n")[0]
            if 4 < len(cand) < 100:
                r.coordenador_lider = cand

    # Agente fiduciário
    bloco = _proxima_dataset(texto, ["Agente Fiduciário"], 200)
    if bloco:
        partes = re.split(r"[:\n]", bloco, maxsplit=2)
        if len(partes) > 1:
            cand = partes[1].strip().split("\n")[0]
            if 4 < len(cand) < 100:
                r.agente_fiduciario = cand

    return r


def _resumir_paragrafo(texto: str, max_chars: int = 400) -> str:
    t = re.sub(r"\s+", " ", texto).strip()
    return t[:max_chars] + ("..." if len(t) > max_chars else "")
