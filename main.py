import time
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# Configuração
ID_CRI = "94856"
URL = f"https://www.vortx.com.br/investidor/dcm/operacao?id={ID_CRI}"

def run():
    print(f"--- Iniciando GitHub Action para ID: {ID_CRI} ---")
    
    # Configurações para rodar no servidor do GitHub (Headless obrigatório)
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    # User-Agent comum para não parecer robô de CI/CD
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(options=options)

    try:
        print(f"Acessando: {URL}")
        driver.get(URL)
        
        # Espera fixa para o site carregar (Vórtx é lento)
        time.sleep(10)
        
        # Pega todo o texto da página
        texto_pagina = driver.find_element(By.TAG_NAME, "body").text
        
        # Verifica bloqueio 444/403
        if "444" in texto_pagina or "working" in texto_pagina:
            print("❌ ERRO: O IP da Microsoft (GitHub) também foi bloqueado.")
        else:
            # Procura pelo Código IF usando Regex
            match = re.search(r"Código IF[\s\n]*[:\-]?[\s\n]*([A-Z0-9]+)", texto_pagina, re.IGNORECASE)
            
            if match:
                codigo = match.group(1)
                print("\n" + "="*40)
                print(f"✅ SUCESSO! CÓDIGO IF: {codigo}")
                print("="*40 + "\n")
            else:
                print("⚠️ Página carregou, mas 'Código IF' não encontrado no texto visível.")
                print("Trecho inicial do texto capturado:")
                print(texto_pagina[:500])

    except Exception as e:
        print(f"Erro de execução: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    run()
