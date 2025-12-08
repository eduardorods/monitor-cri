import time
import pandas as pd
from io import StringIO
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException

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
    
    # Removemos o 'eager' para garantir que os scripts rodem
    # options.page_load_strategy = 'eager' 
    
    driver = webdriver.Chrome(options=options)
    
    # Timeout rígido: Se travar por 60s, ele desiste e segue o baile
    driver.set_page_load_timeout(60)
    driver.set_script_timeout(60)
    
    return driver

def salvar_print(driver, nome):
    try:
        driver.save_screenshot(f"{nome}.png")
        print(f"📸 Screenshot salvo: {nome}.png")
    except:
        pass

def clicar_aba(driver, nome_aba):
    print(f"   > Procurando aba '{nome_aba}'...")
    try:
        # Procura por qualquer elemento clicável com o texto
        xpath = f"//*[contains(text(), '{nome_aba}')]"
        elementos = driver.find_elements(By.XPATH, xpath)
        
        for elem in elementos:
            # Filtra apenas elementos visíveis
            if elem.is_displayed():
                # Tenta clicar no elemento ou no pai dele (caso o texto esteja num span dentro de um botão)
                driver.execute_script("arguments[0].click();", elem)
                time.sleep(5) # Espera o conteúdo carregar após o clique
                return True
        print(f"   > Aba '{nome_aba}' não encontrada ou não clicável.")
        return False
    except Exception as e:
        print(f"   > Erro ao tentar aba {nome_aba}: {e}")
        return False

def extrair_links(driver):
    dados = []
    try:
        # Pega todos os links da página
        links = driver.find_elements(By.TAG_NAME, "a")
        for link in links:
            try:
                href = link.get_attribute('href')
                texto = link.text.strip()
                # Filtros para pegar apenas documentos úteis
                if href and texto and len(texto) > 3:
                    if any(x in href for x in ['id=', '.pdf', 'download', 'visualizar']):
                        dados.append({"Descrição": texto, "Link": href})
            except:
                continue
    except:
        pass
    return dados

def run():
    print(f"--- Iniciando Monitor Vórtx (Com Screenshots) ---")
    driver = setup_driver()
    excel_sheets = {}

    try:
        # 1. Acesso ao Site
        try:
            print("Carregando página...")
            driver.get(URL)
        except TimeoutException:
            print("⚠️ Timeout no carregamento inicial (Site lento). Tentando continuar...")
            driver.execute_script("window.stop();")
        
        # Espera extra para o JS montar a tela
        time.sleep(10)
        salvar_print(driver, "1_pagina_inicial")

        # 2. Verifica se carregou certo
        if "444" in driver.page_source or "working" in driver.page_source:
            print("❌ Bloqueio detectado no HTML.")
            excel_sheets["Erro"] = pd.DataFrame([{"Erro": "Bloqueio 444 detectado"}])
        else:
            # --- ABA PU ---
            print("\n--- Processando PU ---")
            if clicar_aba(driver, "PU"):
                salvar_print(driver, "2_aba_pu")
                try:
                    dfs = pd.read_html(StringIO(driver.page_source))
                    found_pu = False
                    for df in dfs:
                        # Verifica se é a tabela de PU (tem coluna Data e PU)
                        cols = " ".join([str(c).lower() for c in df.columns])
                        if "data" in cols and "pu" in cols:
                            # Tenta filtrar
                            df = df.astype(str) # Converte tudo para texto para facilitar busca
                            col_data = [c for c in df.columns if "Data" in str(c) or "Referência" in str(c)][0]
                            
                            alvo = df[df[col_data].str.contains(DATA_ALVO_PU, na=False)]
                            if not alvo.empty:
                                excel_sheets["PU_Alvo"] = alvo
                                print(f"✅ PU de {DATA_ALVO_PU} encontrado!")
                            else:
                                excel_sheets["PU_Completo"] = df
                                print(f"⚠️ Data {DATA_ALVO_PU} não achada. Salvando tabela inteira.")
                            found_pu = True
                            break
                    if not found_pu:
                        print("Nenhuma tabela de PU reconhecida no HTML.")
                except Exception as e:
                    print(f"Erro ao ler tabela PU: {e}")

            # --- ABA DOCUMENTOS ---
            print("\n--- Processando Documentos ---")
            if clicar_aba(driver, "Documentos"):
                salvar_print(driver, "3_aba_docs")
                docs = extrair_links(driver)
                if docs:
                    excel_sheets["Documentos"] = pd.DataFrame(docs)
                    print(f"✅ {len(docs)} documentos encontrados.")
                else:
                    print("Nenhum link capturado.")

            # --- ABA ASSEMBLEIAS ---
            print("\n--- Processando Assembleias ---")
            if clicar_aba(driver, "Assembleias"):
                salvar_print(driver, "4_aba_assembleias")
                atas = extrair_links(driver)
                if atas:
                    excel_sheets["Assembleias"] = pd.DataFrame(atas)
                    print(f"✅ {len(atas)} assembleias encontradas.")

        # --- GERAÇÃO FINAL ---
        if excel_sheets:
            print(f"\nGerando Excel...")
            with pd.ExcelWriter(NOME_ARQUIVO, engine='openpyxl') as writer:
                for nome, df in excel_sheets.items():
                    df.to_excel(writer, sheet_name=nome[:30], index=False)
            print("Arquivo salvo com sucesso.")
        else:
            print("❌ Nenhuma informação capturada. Gerando Excel de aviso.")
            df_erro = pd.DataFrame([{"Status": "Falha", "Motivo": "Nenhuma tabela ou link encontrado. Verifique os prints."}])
            df_erro.to_excel(NOME_ARQUIVO, index=False)

    except Exception as e:
        print(f"Erro fatal: {e}")
        pd.DataFrame([{"Erro Fatal": str(e)}]).to_excel(NOME_ARQUIVO)
        
    finally:
        driver.quit()

if __name__ == "__main__":
    run()
