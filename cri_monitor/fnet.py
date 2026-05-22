"""Download de documentos do FNet (B3)."""
import os
import re
from typing import Optional

import requests


FNET_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/pdf,application/octet-stream,*/*",
}


def _slugify(nome: str, max_len: int = 80) -> str:
    s = re.sub(r"[^\w\-. ]", "_", nome or "").strip()
    s = re.sub(r"\s+", "_", s)
    return s[:max_len] or "documento"


def baixar_documento(url: str, dir_destino: str, nome_base: str,
                     timeout: int = 60) -> Optional[str]:
    """Baixa um documento (geralmente PDF) do FNet e salva em disco.
    Retorna o caminho do arquivo salvo, ou None se falhar.
    """
    os.makedirs(dir_destino, exist_ok=True)
    try:
        resp = requests.get(url, headers=FNET_HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
    except Exception as e:
        print(f"  Falha ao baixar {url}: {e}")
        return None

    extensao = ".pdf"
    content_type = resp.headers.get("Content-Type", "").lower()
    if "pdf" not in content_type and not resp.content.startswith(b"%PDF"):
        extensao = ".bin"

    caminho = os.path.join(dir_destino, _slugify(nome_base) + extensao)
    with open(caminho, "wb") as f:
        f.write(resp.content)
    return caminho
