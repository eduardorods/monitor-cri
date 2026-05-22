"""Lista local de securitizadoras + resolução nome -> CNPJ por matching fuzzy."""
import re
from typing import Optional

# CNPJs das principais securitizadoras de CRI no Brasil (só dígitos).
SECURITIZADORAS_CONHECIDAS: list[dict] = [
    {"cnpj": "08769451000108", "companyName": "ISEC Securitizadora S.A."},
    {"cnpj": "02773542000122", "companyName": "Opea Securitizadora S.A."},
    {"cnpj": "05786631000147", "companyName": "True Securitizadora S.A."},
    {"cnpj": "11631773000175", "companyName": "Habitasec Securitizadora S.A."},
    {"cnpj": "12130522000141", "companyName": "Virgo Companhia de Securitização"},
    {"cnpj": "08390175000170", "companyName": "Gaia Securitizadora S.A."},
    {"cnpj": "02366571000178", "companyName": "Ápice Securitizadora S.A."},
    {"cnpj": "14643249000151", "companyName": "Eco Securitizadora de Direitos Creditórios do Agronegócio S.A."},
    {"cnpj": "23611298000133", "companyName": "RB Capital Companhia de Securitização"},
    {"cnpj": "01741530000196", "companyName": "Brazilian Securities Companhia de Securitização"},
    {"cnpj": "03767538000146", "companyName": "Cibrasec - Companhia Brasileira de Securitização"},
    {"cnpj": "10753840000176", "companyName": "Barigui Securitizadora S.A."},
    {"cnpj": "18051667000170", "companyName": "Fortesec Companhia de Securitização"},
    {"cnpj": "26444307000148", "companyName": "Polo Capital Securitizadora S.A."},
    {"cnpj": "27396108000143", "companyName": "Vert Companhia Securitizadora"},
    {"cnpj": "36605949000107", "companyName": "Vórtx Companhia Securitizadora"},
    {"cnpj": "40303372000102", "companyName": "Solis Companhia Securitizadora"},
    {"cnpj": "42530249000124", "companyName": "Pátria Securitizadora S.A."},
    {"cnpj": "48795946000100", "companyName": "Octante Securitizadora S.A."},
    {"cnpj": "34380884000147", "companyName": "Riza Securitizadora S.A."},
]

_STOPWORDS = {
    "sa", "s/a", "ltda", "me", "eireli",
    "securitizadora", "securitizadoras",
    "companhia", "cia", "company",
    "direitos", "creditorios", "creditórios",
    "de", "do", "da", "dos", "das",
    "of", "agronegócio", "agronegocio",
    "credito", "crédito", "creditos", "créditos",
    "imobiliarios", "imobiliários",
    "the",
}


def _normalize(name: str) -> set:
    """Reduz o nome a um conjunto de tokens significativos."""
    if not name:
        return set()
    s = name.lower()
    s = re.sub(r"[áàâã]", "a", s)
    s = re.sub(r"[éê]", "e", s)
    s = re.sub(r"[íî]", "i", s)
    s = re.sub(r"[óôõ]", "o", s)
    s = re.sub(r"[úû]", "u", s)
    s = re.sub(r"[ç]", "c", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    tokens = {t for t in s.split() if t and t not in _STOPWORDS and len(t) > 1}
    return tokens


def encontrar_cnpj_por_nome(nome: str) -> Optional[str]:
    """Tenta achar o CNPJ da securitizadora a partir de uma string de nome livre.

    Estratégia:
    1. Match exato do conjunto de tokens normalizados.
    2. Maior interseção (mínimo de 1 token comum e overlap >= 50% do menor lado).
    """
    alvo = _normalize(nome)
    if not alvo:
        return None

    melhor: Optional[dict] = None
    melhor_score = 0.0

    for sec in SECURITIZADORAS_CONHECIDAS:
        cand = _normalize(sec["companyName"])
        if not cand:
            continue
        if cand == alvo:
            return sec["cnpj"]
        intersec = alvo & cand
        if not intersec:
            continue
        score = len(intersec) / min(len(alvo), len(cand))
        if score > melhor_score:
            melhor_score = score
            melhor = sec

    if melhor and melhor_score >= 0.5:
        return melhor["cnpj"]
    return None
