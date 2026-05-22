"""Extrai campos do Termo de Securitização usando a API Gemini (free tier)."""
import json
import os
import sys
from typing import Optional

from cri_monitor.pdf_parser import ResumoOperacao


_PROMPT = """Você é um especialista em direito financeiro brasileiro analisando um Termo de Securitização de CRI (Certificado de Recebíveis Imobiliários).

Extraia as informações solicitadas do texto abaixo e retorne em JSON. Se um campo não estiver presente, use null.

Campos:
- devedor: nome completo (razão social) da empresa devedora dos créditos imobiliários
- cnpj_devedor: CNPJ do devedor, formato XX.XXX.XXX/XXXX-XX
- valor_total: valor total da emissão em reais, formato "R$ X.XXX.XXX,XX"
- data_emissao: data de emissão, formato DD/MM/AAAA
- data_vencimento: data de vencimento, formato DD/MM/AAAA
- taxa_remuneracao: descrição completa da remuneração (ex: "CDI + 1,5% a.a.", "IPCA + 6,50% a.a.")
- indice_atualizacao: índice de atualização monetária (IPCA, IGP-M, CDI, TR, SELIC, etc.) ou null se for taxa pré-fixada
- lastro: descrição resumida (até 400 caracteres) dos créditos imobiliários que servem de lastro à operação
- coordenador_lider: nome completo da instituição coordenadora líder da oferta
- agente_fiduciario: nome completo da empresa agente fiduciária
- garantias: lista de strings com os tipos de garantias da operação (ex: ["Alienação Fiduciária de Imóvel", "Cessão Fiduciária de Direitos Creditórios", "Fiança", "Fundo de Reserva"])

Texto do Termo de Securitização:

\"\"\"
{texto}
\"\"\"

Retorne APENAS o JSON, sem comentários ou texto adicional."""


_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "devedor": {"type": "string", "nullable": True},
        "cnpj_devedor": {"type": "string", "nullable": True},
        "valor_total": {"type": "string", "nullable": True},
        "data_emissao": {"type": "string", "nullable": True},
        "data_vencimento": {"type": "string", "nullable": True},
        "taxa_remuneracao": {"type": "string", "nullable": True},
        "indice_atualizacao": {"type": "string", "nullable": True},
        "lastro": {"type": "string", "nullable": True},
        "coordenador_lider": {"type": "string", "nullable": True},
        "agente_fiduciario": {"type": "string", "nullable": True},
        "garantias": {"type": "array", "items": {"type": "string"}},
    },
}


def analisar_com_gemini(texto: str, api_key: Optional[str] = None,
                       max_chars: int = 400_000) -> Optional[ResumoOperacao]:
    """Extrai campos via Gemini Flash. Retorna None se a API key faltar ou erro."""
    api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")
    if not api_key or not texto:
        return None

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("  Pacote google-genai não instalado.", file=sys.stderr)
        return None

    texto_limitado = texto[:max_chars]
    prompt = _PROMPT.format(texto=texto_limitado)

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_RESPONSE_SCHEMA,
                temperature=0.0,
            ),
        )
        data = json.loads(response.text)
    except Exception as e:
        print(f"  Erro no Gemini: {e}", file=sys.stderr)
        return None

    return ResumoOperacao(
        devedor=data.get("devedor"),
        cnpj_devedor=data.get("cnpj_devedor"),
        valor_total=data.get("valor_total"),
        data_emissao=data.get("data_emissao"),
        data_vencimento=data.get("data_vencimento"),
        taxa_remuneracao=data.get("taxa_remuneracao"),
        indice_atualizacao=data.get("indice_atualizacao"),
        lastro=data.get("lastro"),
        coordenador_lider=data.get("coordenador_lider"),
        agente_fiduciario=data.get("agente_fiduciario"),
        garantias=data.get("garantias") or [],
    )
