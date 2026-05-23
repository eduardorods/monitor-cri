"""Extrai campos do Termo de Securitização usando a API Gemini (free tier)."""
import json
import os
import sys
from typing import Optional

from cri_monitor.pdf_parser import ResumoOperacao


_PROMPT = """Você é um especialista em direito financeiro brasileiro analisando um Termo de Securitização de CRI (Certificado de Recebíveis Imobiliários).

Extraia as informações abaixo do texto e retorne em JSON. Se um campo não estiver presente, use null ou lista vazia.

CAMPOS BÁSICOS:
- devedor: nome completo (razão social) da empresa devedora
- cnpj_devedor: CNPJ do devedor, formato XX.XXX.XXX/XXXX-XX
- valor_total: valor total da emissão, formato "R$ X.XXX.XXX,XX"
- data_emissao: data de emissão, formato DD/MM/AAAA
- data_vencimento: data de vencimento final, formato DD/MM/AAAA
- taxa_remuneracao: descrição completa da remuneração (ex: "CDI + 1,5% a.a.", "IPCA + 6,50% a.a.")
- indice_atualizacao: índice de atualização monetária (IPCA, IGP-M, CDI, TR, SELIC, etc.)
- lastro: descrição resumida (até 400 caracteres) dos créditos imobiliários que servem de lastro
- coordenador_lider: nome da instituição coordenadora líder
- agente_fiduciario: nome da empresa agente fiduciária

CRONOGRAMA DE PAGAMENTOS:
- cronograma_descricao: descrição textual do cronograma (ex: "Juros mensais a partir de DD/MM/AAAA. Amortizações trimestrais a partir de DD/MM/AAAA, sendo X% ao trimestre até o vencimento em DD/MM/AAAA"). Inclua periodicidade dos juros, data do primeiro pagamento de juros, regime de amortização (SAC, Price, bullet, etc.), periodicidade e data de início das amortizações.

GARANTIAS DETALHADAS:
- garantias: lista simples dos tipos de garantia (ex: ["Alienação Fiduciária de Imóvel", "Cessão Fiduciária", "Fiança"])
- garantias_detalhadas: descrição completa de cada garantia em texto corrido (até 800 caracteres). Para imóveis: endereço/localização e matrícula. Para cessão fiduciária: quais direitos/recebíveis. Para fiança: quem é o fiador. Para fundo de reserva: valor ou percentual.

COVENANTS (cláusulas de vencimento antecipado ou obrigações financeiras):
- covenants: lista de strings, uma por covenant. Cada string deve descrever o covenant completo. Exemplos: "LTV máximo de 70% — calculado sobre o valor de avaliação do imóvel dado em garantia", "Índice de Cobertura do Serviço da Dívida (DSCR) mínimo de 1,3x — medido semestralmente", "Razão de garantia mínima de 130% do saldo devedor". Se não houver covenants financeiros, retorne lista vazia.

TABELA DO CRONOGRAMA DE PAGAMENTOS:
- tabela_cronograma: lista de objetos com o cronograma detalhado extraído do Anexo ou tabela do Termo. Cada objeto deve ter os campos disponíveis dentre: {"data": "DD/MM/AAAA", "evento": "Juros/Amortização/Principal", "percentual_amortizacao": "X%", "valor_parcela": "R$ X", "saldo_devedor": "R$ X", "observacao": "..."}. Se não encontrar tabela, retorne lista vazia.

SÉRIES DA EMISSÃO:
- serie_unica: true se a emissão tem apenas uma série, false se tiver mais de uma série.
- series: lista de objetos descrevendo cada série. Se for série única, retorne uma lista com um único objeto. Cada objeto deve conter os campos disponíveis dentre: {"serie": "1ª Série", "valor": "R$ X.XXX.XXX,XX", "quantidade_titulos": "X CRIs", "remuneracao": "CDI + 1,5% a.a.", "indice": "CDI", "data_emissao": "DD/MM/AAAA", "data_vencimento": "DD/MM/AAAA", "descricao": "descrição adicional relevante da série"}.

Texto do Termo de Securitização:

\"\"\"
{texto}
\"\"\"

Retorne APENAS o JSON, sem comentários ou texto adicional."""


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
    prompt = _PROMPT.replace("{texto}", texto_limitado)

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
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
        cronograma_descricao=data.get("cronograma_descricao"),
        garantias_detalhadas=data.get("garantias_detalhadas"),
        covenants=data.get("covenants") or [],
        tabela_cronograma=data.get("tabela_cronograma") or [],
        serie_unica=data.get("serie_unica"),
        series=data.get("series") or [],
    )


_PROMPT_ATA = """Você está analisando uma Ata de Assembleia de Debenturistas/CRI (Certificado de Recebíveis Imobiliários) brasileira.

Extraia as informações abaixo e retorne em JSON. Se um campo não estiver presente, use null.

- data_assembleia: data em que a assembleia foi realizada, formato DD/MM/AAAA
- tipo_assembleia: tipo (ex: "Assembleia Geral Ordinária", "Assembleia Geral Extraordinária", "Assembleia Especial")
- deliberacoes: texto corrido (até 600 caracteres) descrevendo as principais deliberações e decisões tomadas na assembleia. Seja objetivo e inclua o resultado de cada votação relevante (aprovado, rejeitado, aprovado por maioria, etc.).

Texto da Ata:

\"\"\"
{texto}
\"\"\"

Retorne APENAS o JSON, sem comentários ou texto adicional."""


def analisar_ata_com_gemini(texto: str, nome_arquivo: str,
                            api_key: Optional[str] = None,
                            max_chars: int = 100_000) -> Optional[dict]:
    """Analisa uma ata de assembleia. Retorna dict com data, tipo e deliberações."""
    api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")
    if not api_key or not texto:
        return None

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return None

    prompt = _PROMPT_ATA.replace("{texto}", texto[:max_chars])

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
            ),
        )
        data = json.loads(response.text)
    except Exception as e:
        print(f"  Erro no Gemini ao analisar ata: {e}", file=sys.stderr)
        return None

    return {
        "arquivo": nome_arquivo,
        "data_assembleia": data.get("data_assembleia"),
        "tipo_assembleia": data.get("tipo_assembleia"),
        "deliberacoes": data.get("deliberacoes"),
    }
