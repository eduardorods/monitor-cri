import time
import pandas as pd
from io import StringIO
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- CONFIGURAÇÃO ---
ID_CRI = "94856"
URL = f"https://www.vortx.com.br/investidor/dcm/operacao?id={ID_CRI}"
DATA_ALVO_PU = "08/12/2025" # Data que você quer buscar na tabela de PU
NOME_ARQUIVO = "dados_cri_vortx.xlsx"

def setup_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    return webdriver.Chrome(options=options)

def clicar_aba(driver, nome_aba):
    """Função robusta para achar e clicar nas abas"""
    print(f"Tentando clicar na aba '{nome_aba}'...")
    try:
        # Tenta achar links ou botões que contenham o texto da aba
        # O xpath procura: qualquer elemento 'a' ou 'div' ou 'span' que tenha o texto exato ou parcial
        xpath = f"//*[self::a or self::div or self::span or self::button][contains(text(), '{nome_aba}')]"
        elementos = driver.find_elements(By.XPATH, xpath)
        
        for elem in elementos:
            # Verifica se o elemento está visível e clicável
            if elem.is_displayed():
                driver.execute_script("arguments[0].click();", elem)
                time.sleep(5) # Espera o conteúdo da aba carregar
                print(f"Aba '{nome_aba}' clicada com sucesso.")
                return True
        print(f"Aviso: Não encontrei elemento clicável para aba '{nome_aba}'.")
        return False
    except Exception as e:
        print(f"Erro ao clicar na aba {nome_aba}: {e}")
        return False

def extrair_links(driver):
    """Extrai texto e href de todos os links visíveis na área de conteúdo"""
    dados = []
    try:
        # Pega links que parecem documentos (PDFs ou visualizações)
        links = driver.find_elements(By.TAG_NAME, "a")
        for link in links:
            href = link.get_attribute('href')
            texto = link.text.strip()
            
            # Filtra apenas links relevantes (com download, pdf ou visualizar) e que tenham texto
            if href and texto and ('id=' in href or '.pdf' in href or 'download' in href or 'visualizar' in href):
                # Evita links de menu/navegação
                if len(texto) > 3: 
                    dados.append({"Documento": texto, "Link": href})
    except Exception as e:
        print(f"Erro ao extrair links: {e}")
    return dados

def run():
    print(f"--- Iniciando Extração Completa para ID: {ID_CRI} ---")
    driver = setup_driver()
    
    # Dicionário para guardar os DataFrames de cada aba do Excel
    excel_sheets = {}

    try:
        driver.get(URL)
        time.sleep(10) # Espera inicial do site
        
        # --- PARTE 1: PU ---
        if clicar_aba(driver, "PU"):
            print("Processando tabela de PU...")
            try:
                # O Pandas lê as tabelas HTML automaticamente
                dfs = pd.read_html(StringIO(driver.page_source))
                tabela_pu = pd.DataFrame()
                
                # Procura qual tabela tem a coluna "Data" e "PU"
                for df in dfs:
                    cols = [c.lower() for c in df.columns]
                    if any("data" in c for c in cols) and any("pu" in c for c in cols):
                        tabela_pu = df
                        break
                
                if not tabela_pu.empty:
                    # Filtra pela data específica
                    # Normaliza nomes de colunas para facilitar
                    tabela_pu.columns = [c.strip() for c in tabela_pu.columns]
                    
                    # Tenta achar a linha da data alvo
                    # Assume que a coluna de data é a primeira ou tem 'Data' no nome
                    col_data = [c for c in tabela_pu.columns if "Data" in c or "Referência" in c][0]
                    
                    # Filtra
                    resultado_pu = tabela_pu[tabela_pu[col_data] == DATA_ALVO_PU]
                    
                    if not resultado_pu.empty:
                        print(f"PU encontrado para {DATA_ALVO_PU}!")
                        excel_sheets["PU"] = resultado_pu
                    else:
                        print(f"Data {DATA_ALVO_PU} não encontrada na tabela visível. Salvando tabela completa.")
                        excel_sheets["PU"] = tabela_pu # Salva tudo se não achar a data exata
                else:
                    print("Nenhuma tabela de PU identificada.")
            except Exception as e:
                print(f"Erro ao processar PU: {e}")

        # --- PARTE 2: Documentos ---
        # Recarrega ou clica na aba (se necessário)
        if clicar_aba(driver, "Documentos"):
            print("Extraindo Documentos...")
            docs_data = extrair_links(driver)
            if docs_data:
                excel_sheets["Documentos"] = pd.DataFrame(docs_data)
                print(f"Encontrados {len(docs_data)} documentos.")
            else:
                excel_sheets["Documentos"] = pd.DataFrame([{"Aviso": "Nenhum documento encontrado"}])

        # --- PARTE 3: Assembleias ---
        if clicar_aba(driver, "Assembleias"):
            print("Extraindo Assembleias...")
            ass_data = extrair_links(driver)
            if ass_data:
                excel_sheets["Assembleias"] = pd.DataFrame(ass_data)
                print(f"Encontradas {len(ass_data)} assembleias.")
            else:
                excel_sheets["Assembleias"] = pd.DataFrame([{"Aviso": "Nenhuma assembleia encontrada"}])

        # --- GERAÇÃO DO ARQUIVO EXCEL ---
        if excel_sheets:
            with pd.ExcelWriter(NOME_ARQUIVO, engine='openpyxl') as writer:
                for sheet_name, df in excel_sheets.items():
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
            print(f"\n✅ Arquivo Excel gerado com sucesso com as abas: {list(excel_sheets.keys())}")
        else:
            print("❌ Nenhum dado foi coletado para gerar o Excel.")

    except Exception as e:
        print(f"Erro fatal: {e}")
        
    finally:
        driver.quit()

if __name__ == "__main__":
    run()
