import time
import pandas as pd
from io import StringIO
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException

# --- CONFIGURAÇÃO ---
ID_CRI = "94856"
URL = f"https://www.vortx.com.br/investidor/dcm/operacao?id={ID_CRI}"
DATA_ALVO_PU = "08/12/2025"
NOME_ARQUIVO = "dados_cri_vortx.xlsx"

def setup_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # --- PROTEÇÃO ANTI-TRAVAMENTO 1 ---
    # 'eager': O navegador libera o controle assim que o HTML baixa, 
    # sem esperar imagens ou estilos terminarem.
    options.page_load_strategy = 'eager'
    
    driver = webdriver.Chrome(options=options)
    
    # --- PROTEÇÃO ANTI-TRAVAMENTO 2 ---
    # Se uma ação demorar mais de 60 segundos, o driver aborta com erro
    driver.set_page_load_timeout(60)
    driver.set_script_timeout(60)
    
    return driver

def clicar_aba(driver, nome_aba):
    print(f"   > Procurando aba '{nome_aba}'...")
    try:
        # Tenta achar links ou botões que contenham o texto da aba
        xpath = f"//*[self::a or self::div or self::span][contains(text(), '{nome_aba}')]"
        elementos = driver.find_elements(By.XPATH, xpath)
        
        for elem in elementos:
            if elem.is_displayed():
                # Clica via Javascript para evitar travamento de UI
                driver.execute_script("arguments[0].click();", elem)
                time.sleep(5) # Espera fixa segura
                print(f"   > Aba '{nome_aba}' clicada.")
                return True
        return False
    except Exception as e:
        print(f"   > Aviso: Não foi possível clicar na aba {nome_aba}. Erro: {str(e)[:100]}")
        return False

def extrair_links(driver):
    dados = []
    try:
        links = driver.find_elements(By.TAG_NAME, "a")
        for link in links:
            try:
                href = link.get_attribute('href')
                texto = link.text.strip()
                if href and texto and ('id=' in href or '.pdf' in href or 'download' in href or 'visualizar' in href):
                    if len(texto) > 3: 
                        dados.append({"Descrição": texto, "Link": href})
            except:
                continue # Se um link falhar, pula para o próximo
    except Exception as e:
        print(f"Erro ao ler links: {e}")
    return dados

def run():
    print(f"--- Iniciando (Timeout configurado para 60s por ação) ---")
    print(f"Alvo: {URL}")
    
    driver = setup_driver()
    excel_sheets = {}

    try:
        # Acesso Inicial com Tratamento de Timeout
        try:
            driver.get(URL)
        except TimeoutException:
            print("⚠️ Alerta: O site demorou muito para carregar, mas vamos tentar continuar com o que baixou.")
            driver.execute_script("window.stop();") # Força parada do carregamento
        
        time.sleep(5) # Espera o Javascript renderizar o básico
        
        # --- 1. PU ---
        print("\n[1/3] Processando PU...")
        if clicar_aba(driver, "PU"):
            try:
                # Limita a leitura a tabelas visíveis
                html = driver.page_source
                if "<table" in html:
                    dfs = pd.read_html(StringIO(html))
                    for df in dfs:
                        cols = [str(c).lower() for c in df.columns]
                        if any("data" in c for c in cols) and any("pu" in c for c in cols):
                            # Limpeza e Filtro
                            tabela_pu = df.copy()
                            col_data = [c for c in tabela_pu.columns if "Data" in str(c) or "Referência" in str(c)][0]
                            # Filtra pela data
                            resultado = tabela_pu[tabela_pu[col_data].astype(str).str.contains(DATA_ALVO_PU, na=False)]
                            
                            if not resultado.empty:
                                excel_sheets["PU_Alvo"] = resultado
                                print(f"   > PU de {DATA_ALVO_PU} encontrado!")
                            else:
                                excel_sheets["PU_Historico"] = tabela_pu.head(20) # Salva as 20 ultimas se nao achar
                                print(f"   > Data não encontrada. Salvando histórico recente.")
                            break
            except Exception as e:
                print(f"   > Erro no processamento de PU: {e}")

        # --- 2. Documentos ---
        print("\n[2/3] Processando Documentos...")
        # Recarrega a página para limpar o estado se necessário, ou clica direto
        if clicar_aba(driver, "Documentos"):
            docs = extrair_links(driver)
            if docs:
                excel_sheets["Documentos"] = pd.DataFrame(docs)
                print(f"   > {len(docs)} documentos listados.")

        # --- 3. Assembleias ---
        print("\n[3/3] Processando Assembleias...")
        if clicar_aba(driver, "Assembleias"):
            atas = extrair_links(driver)
            if atas:
                excel_sheets["Assembleias"] = pd.DataFrame(atas)
                print(f"   > {len(atas)} assembleias listadas.")

        # --- FIM ---
        if excel_sheets:
            print(f"\nGerando Excel com abas: {list(excel_sheets.keys())}...")
            with pd.ExcelWriter(NOME_ARQUIVO, engine='openpyxl') as writer:
                for nome, df in excel_sheets.items():
                    df.to_excel(writer, sheet_name=nome[:30], index=False) # Excel limita nome de aba a 31 chars
            print("✅ Sucesso!")
        else:
            print("❌ Nenhum dado coletado.")

    except Exception as e:
        print(f"❌ Erro Crítico no Script: {e}")
        
    finally:
        print("Fechando navegador...")
        try:
            driver.quit()
        except:
            pass

if __name__ == "__main__":
    run()
