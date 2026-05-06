"""
Envia um arquivo para o Google Drive.

Uso:
    python upload_drive.py <caminho_do_arquivo>

Variáveis de ambiente obrigatórias:
    GOOGLE_CREDENTIALS     — JSON da conta de serviço (conteúdo completo)
    GOOGLE_DRIVE_FOLDER_ID — ID da pasta de destino no Google Drive
"""
import json
import os
import sys

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def upload(file_path: str) -> str:
    credentials_json = os.environ.get("GOOGLE_CREDENTIALS", "")
    folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "")

    if not credentials_json or not folder_id:
        print("GOOGLE_CREDENTIALS ou GOOGLE_DRIVE_FOLDER_ID não configurados. Pulando upload.", flush=True)
        return ""

    credentials = service_account.Credentials.from_service_account_info(
        json.loads(credentials_json), scopes=SCOPES
    )
    service = build("drive", "v3", credentials=credentials)

    file_name = os.path.basename(file_path)
    media = MediaFileUpload(file_path, resumable=True)
    metadata = {"name": file_name, "parents": [folder_id]}

    result = service.files().create(
        body=metadata,
        media_body=media,
        fields="id,webViewLink",
    ).execute()

    link = result.get("webViewLink", "")
    print(f"Arquivo enviado ao Google Drive: {link}", flush=True)
    return link


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python upload_drive.py <arquivo>")
        sys.exit(1)
    upload(sys.argv[1])
