import time
import pandas as pd
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from io import StringIO

# --- CONFIGURAÇÃO ---
ID_CRI = "94856"
URL = f"https://www.vortx.com.br/investidor/dcm/operacao?id={ID_CRI}"
DATA_ALVO_PU = "08/12/2025"  # A data que você procura
NOME_ARQUIVO = "dados_cri_vortx.xlsx"

def setup_driver():
    print("Configurando navegador indetectável...")
    options = uc.ChromeOptions()
    # O modo headless=new é vital para não ser detectado em servidores Linux
    options.add_argument('--headless=new') 
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--lang=pt-BR')
    
    # Inicializa o driver "stealth"
    driver = uc.Chrome(options=options, version_main=142)
    driver.set_page_load_timeout(60)
    return driver

def clicar_aba(driver, nome_aba):
    """Clica na aba garantindo que o JS processou o clique"""
    print(f"   > Procurando aba '{nome_aba}'...")
    try:
        # Procura por links ou divs que contenham o texto da aba
        elementos = driver.find_elements(By.XPATH, f"//*[contains(text(), '{nome_aba}')]")
        for elem in elementos:
            if elem.is_displayed():
                driver.execute_script("arguments[0].click();", elem)
                time.sleep(5) # Pausa tática para o conteúdo carregar
                return True
        return False
    except:
        return False

def extrair_links_download(driver):
    """Captura nome e link de arquivos PDF/Download"""
    lista = []
    try:
        # Pega todas as tags 'a' da página
        links = driver.find_elements(By.TAG_NAME, "a")
        for link in links:
            try:
                url = link.get_attribute('href')
                texto = link.text.strip()
                
                # Filtra apenas o que parece ser documento relevante
                if url and texto and len(texto) > 3:
                    if any(term in url for term in ['.pdf', 'download', 'visualizar', 'id=']):
                        lista.append({"Documento": texto, "Link": url})
            except:
                continue
    except Exception as e:
        print(f"Erro ao ler links: {e}")
    return lista

def run():
    print(f"--- Iniciando Robô Blindado para ID: {ID_CRI} ---")
    driver = None
    excel_sheets = {}
    
    try:
        driver = setup_driver()
        print(f"Acessando: {URL}")
        driver.get(URL)
        
        # Espera inicial para passar pelo desafio do firewall (se houver)
        time.sleep(10)
        
        # Verificação de Bloqueio 444/403
        titulo = driver.title
        print(f"Título da página: {titulo}")
        if "444" in driver.page_source or "Access Denied" in driver.page_source:
            raise Exception("Bloqueio de IP detectado mesmo com modo Stealth.")

        # --- 1. BUSCA PU ---
        print("\n[1] Processando Tabela de PU...")
        if clicar_aba(driver, "PU"):
            try:
                html = driver.page_source
                # Pandas lê todas as tabelas visíveis
                dfs = pd.read_html(StringIO(html))
                
                tabela_encontrada = False
                for df in dfs:
                    # Converte colunas para string minúscula para facilitar busca
                    cols = " ".join([str(c).lower() for c in df.columns])
                    
                    if "data" in cols and "pu" in cols:
                        tabela_encontrada = True
                        print("   > Tabela de PU localizada.")
                        
                        # Limpeza dos dados
                        df = df.astype(str)
                        # Identifica a coluna de data (geralmente a primeira ou com nome Data)
                        col_data = [c for c in df.columns if "Data" in str(c) or "Referência" in str(c)][0]
                        
                        # Filtra pela data alvo
                        resultado = df[df[col_data].str.contains(DATA_ALVO_PU, na=False)]
                        
                        if not resultado.empty:
                            print(f"   > ✅ SUCESSO: PU de {DATA_ALVO_PU} encontrado!")
                            excel_sheets["PU_Alvo"] = resultado
                        else:
                            print(f"   > Aviso: Data {DATA_ALVO_PU} não encontrada. Salvando as 30 últimas.")
                            excel_sheets["PU_Recentes"] = df.head(30)
                        break
                
                if not tabela_encontrada:
                    print("   > Nenhuma estrutura de tabela de PU encontrada.")
                    
            except Exception as e:
                print(f"   > Erro ao processar tabela PU: {e}")

        # --- 2. DOCUMENTOS ---
        print("\n[2] Processando Documentos...")
        # Força refresh ou clique na aba Documentos
        if clicar_aba(driver, "Documentos"):
            docs = extrair_links_download(driver)
            if docs:
                print(f"   > {len(docs)} documentos listados.")
                excel_sheets["Documentos"] = pd.DataFrame(docs)
            else:
                print("   > Nenhum documento encontrado na aba.")

        # --- 3. ASSEMBLEIAS ---
        print("\n[3] Processando Assembleias...")
        if clicar_aba(driver, "Assembleias"):
            atas = extrair_links_download(driver)
            if atas:
                print(f"   > {len(atas)} registros de assembleia encontrados.")
                excel_sheets["Assembleias"] = pd.DataFrame(atas)
            else:
                print("   > Nenhuma assembleia encontrada.")

        # --- SALVAR EXCEL ---
        if excel_sheets:
            print(f"\nGerando arquivo {NOME_ARQUIVO}...")
            with pd.ExcelWriter(NOME_ARQUIVO, engine='openpyxl') as writer:
                for nome, df in excel_sheets.items():
                    # Excel aceita no máx 31 caracteres no nome da aba
                    df.to_excel(writer, sheet_name=nome[:30], index=False)
            print("✅ Arquivo gerado com sucesso!")
        else:
            print("❌ Falha: Nenhum dado foi coletado.")
            # Gera um arquivo de aviso
            pd.DataFrame([{"Status": "Sem dados", "Motivo": "Bloqueio ou falha de leitura"}]).to_excel(NOME_ARQUIVO)

    except Exception as e:
        print(f"Erro Fatal: {e}")
        pd.DataFrame([{"Erro": str(e)}]).to_excel(NOME_ARQUIVO)

    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    run()
