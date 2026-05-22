"""
Envia arquivos para o Google Drive, organizando em subpastas.

Uso:
    python upload_drive.py <caminho1> [<caminho2> ...] --subpasta CRIs/22I1560033

Variáveis de ambiente obrigatórias:
    GOOGLE_CREDENTIALS     — JSON da conta de serviço (conteúdo completo)
    GOOGLE_DRIVE_FOLDER_ID — ID da pasta raiz no Google Drive
"""
import argparse
import json
import os
import sys
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
FOLDER_MIME = "application/vnd.google-apps.folder"


def _service():
    credentials_json = os.environ.get("GOOGLE_CREDENTIALS", "")
    if not credentials_json:
        return None
    credentials = service_account.Credentials.from_service_account_info(
        json.loads(credentials_json), scopes=SCOPES
    )
    return build("drive", "v3", credentials=credentials)


def _achar_ou_criar_pasta(service, nome: str, parent_id: str) -> str:
    """Retorna o ID da pasta com `nome` dentro de `parent_id`; cria se não existir."""
    query = (
        f"mimeType = '{FOLDER_MIME}' and "
        f"name = '{nome.replace(chr(39), chr(92) + chr(39))}' and "
        f"'{parent_id}' in parents and trashed = false"
    )
    resp = service.files().list(q=query, fields="files(id,name)", pageSize=10).execute()
    arquivos = resp.get("files", [])
    if arquivos:
        return arquivos[0]["id"]
    metadata = {"name": nome, "mimeType": FOLDER_MIME, "parents": [parent_id]}
    nova = service.files().create(body=metadata, fields="id").execute()
    return nova["id"]


def _resolver_subpasta(service, base_id: str, subpasta: Optional[str]) -> str:
    if not subpasta:
        return base_id
    pid = base_id
    for parte in subpasta.split("/"):
        parte = parte.strip()
        if parte:
            pid = _achar_ou_criar_pasta(service, parte, pid)
    return pid


def upload(caminhos: list[str], subpasta: Optional[str] = None) -> list[str]:
    service = _service()
    base_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "")
    if service is None or not base_id:
        print("GOOGLE_CREDENTIALS ou GOOGLE_DRIVE_FOLDER_ID não configurados. Pulando upload.",
              flush=True)
        return []

    destino_id = _resolver_subpasta(service, base_id, subpasta)
    links = []
    for caminho in caminhos:
        if not os.path.isfile(caminho):
            print(f"  Aviso: arquivo não encontrado: {caminho}")
            continue
        nome = os.path.basename(caminho)
        media = MediaFileUpload(caminho, resumable=True)
        try:
            result = service.files().create(
                body={"name": nome, "parents": [destino_id]},
                media_body=media,
                fields="id,webViewLink",
            ).execute()
        except HttpError as e:
            print(f"  Falha ao enviar {nome}: {e}")
            continue
        link = result.get("webViewLink", "")
        print(f"  Enviado: {nome} -> {link}", flush=True)
        links.append(link)
    return links


def _parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("arquivos", nargs="+", help="Arquivos a enviar")
    p.add_argument("--subpasta", default=None,
                   help="Caminho de subpastas (ex.: 'CRIs/22I1560033'). Cria se não existir.")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    upload(args.arquivos, args.subpasta)
