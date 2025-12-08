import time
import re
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- CONFIGURAÇÃO ---
ID_CRI = "94856"
URL = f"https://www.vortx.com.br/investidor/dcm/operacao?id={ID_CRI}"
NOME_ARQUIVO = "dados_cri_vortx.xlsx"

def setup_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    return webdriver.Chrome(options=options)

def buscar_valor_por_texto(driver, termos_busca):
    """
    Tenta encontrar um valor na página procurando por rótulos de texto (ex: 'Remuneração').
    Retorna o texto do elemento seguinte ou do pai, dependendo da estrutura.
    """
    for termo in termos_busca:
        try:
            # Estratégia 1: Procura um elemento que contenha o texto e pega o próximo elemento (sibling)
            # Muito comum em estruturas <dt>Label</dt> <dd>Valor</dd> ou <div>Label</div> <div>Valor</div>
            xpath = f"//*[contains(text(), '{termo}')]/following-sibling::*[1]"
            elemento = driver.find_element(By.XPATH, xpath)
            if elemento.text.strip():
                return elemento.text.strip()
            
            # Estratégia 2: Pega o pai e vê se o valor está dentro (ex: <div>Label: Valor</div>)
            xpath_pai = f"//*[contains(text(), '{termo}')]/.."
            elemento_pai = driver.find_element(By.XPATH, xpath_pai)
            texto_pai = elemento_pai.text.replace(termo, "").strip()
            # Limpa caracteres extras como ":" ou "-"
            texto_pai = re.sub(r"^[:\-\s]+", "", texto_pai)
            if texto_pai:
                return texto_pai

        except:
            continue
    return "Não encontrado"

def run():
    print(f"--- Iniciando Extração Detalhada para ID: {ID_CRI} ---")
    driver = setup_driver()
    
    dados = {
        "ID Vórtx": ID_CRI,
        "Data Extração": time.strftime("%d/%m/%Y")
    }

    try:
        driver.get(URL)
        # Espera generosa para garantir carregamento dos componentes
        time.sleep(12)
        
        # 1. Dados Básicos (Geralmente no topo ou Visão Geral)
        # Mapeamento: "Nome da Coluna no Excel": ["Possíveis nomes no site"]
        mapa_campos = {
            "Emissor": ["Emissor", "Devedor", "Cedente"],
            "Código IF": ["Código IF", "Ticker", "Código"],
            "Volume Emitido": ["Volume Total", "Valor da Emissão", "Volume Emitido"],
            "Quantidade Emitida": ["Quantidade", "Qtd. Emitida"],
            "PU de Emissão": ["PU de Emissão", "Valor Unitário", "Preço Unitário"],
            "Data de Emissão": ["Data de Emissão", "Início"],
            "Data de Vencimento": ["Vencimento", "Data de Vencimento"],
            "Remuneração": ["Taxa", "Remuneração", "Juros"],
            "Pagamento de Juros": ["Pagamento de Juros", "Periodicidade Juros"],
            "Amortização": ["Amortização", "Periodicidade Amortização"],
            "Distribuição": ["Distribuição", "Tipo de Oferta"],
            "Tipo de Risco": ["Risco", "Rating", "Classificação de Risco"],
        }

        # Extração automática baseada no mapa
        for campo, termos in mapa_campos.items():
            valor = buscar_valor_por_texto(driver, termos)
            dados[campo] = valor
            print(f"> {campo}: {valor}")

        # 2. Tratamento Especial: Garantias
        # Garantias costumam ser textos longos ou estar em abas.
        # Vamos tentar pegar o bloco de texto se houver uma seção específica.
        print("Buscando Garantias...")
        try:
            # Tenta clicar na aba garantias se existir
            abas = driver.find_elements(By.TAG_NAME, "a")
            for aba in abas:
                if "Garantia" in aba.text:
                    driver.execute_script("arguments[0].click();", aba)
                    time.sleep(3)
                    break
            
            # Pega o texto da área visível ou procura pelo termo
            garantias = buscar_valor_por_texto(driver, ["Garantias", "Descrição das Garantias"])
            dados["Garantias"] = garantias
        except:
            dados["Garantias"] = "Erro ao buscar garantias"

        # 3. Geração do Excel
        df = pd.DataFrame([dados])
        df.to_excel(NOME_ARQUIVO, index=False)
        print(f"\n✅ Excel gerado com sucesso: {NOME_ARQUIVO}")

    except Exception as e:
        print(f"Erro fatal: {e}")
        # Gera um excel de erro para não quebrar o workflow
        pd.DataFrame([{"Erro": str(e)}]).to_excel(NOME_ARQUIVO)
        
    finally:
        driver.quit()

if __name__ == "__main__":
    run()
