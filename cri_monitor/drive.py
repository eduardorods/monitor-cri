"""Helpers para Google Drive: upload, download, listagem e detecção de manuais."""
import os
import sys
from typing import Optional


SCOPES = ["https://www.googleapis.com/auth/drive.file"]
FOLDER_MIME = "application/vnd.google-apps.folder"


def obter_servico():
    """Retorna o service do Google Drive autenticado, ou None se credenciais ausentes."""
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN", "")
    if not (client_id and client_secret and refresh_token):
        return None
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        return None
    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    return build("drive", "v3", credentials=credentials)


def achar_ou_criar_pasta(service, nome: str, parent_id: str,
                         criar: bool = True) -> Optional[str]:
    """Retorna ID da pasta `nome` em `parent_id`. Cria se ausente e criar=True."""
    nome_esc = nome.replace("'", "\\'")
    query = (f"mimeType = '{FOLDER_MIME}' and name = '{nome_esc}' "
             f"and '{parent_id}' in parents and trashed = false")
    resp = service.files().list(q=query, fields="files(id,name)", pageSize=10).execute()
    arquivos = resp.get("files", [])
    if arquivos:
        return arquivos[0]["id"]
    if not criar:
        return None
    metadata = {"name": nome, "mimeType": FOLDER_MIME, "parents": [parent_id]}
    nova = service.files().create(body=metadata, fields="id").execute()
    return nova["id"]


def resolver_subpasta(service, base_id: str, subpasta: Optional[str],
                      criar: bool = True) -> Optional[str]:
    if not subpasta:
        return base_id
    pid = base_id
    for parte in subpasta.split("/"):
        parte = parte.strip()
        if not parte:
            continue
        pid = achar_ou_criar_pasta(service, parte, pid, criar=criar)
        if pid is None:
            return None
    return pid


def listar_arquivos(service, folder_id: str) -> list[dict]:
    """Lista arquivos (não-pastas) na pasta. Retorna [{id, name, mimeType}, ...]."""
    arquivos = []
    page_token = None
    while True:
        resp = service.files().list(
            q=(f"'{folder_id}' in parents and trashed = false "
               f"and mimeType != '{FOLDER_MIME}'"),
            fields="nextPageToken, files(id, name, mimeType)",
            pageSize=100,
            pageToken=page_token,
        ).execute()
        arquivos.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return arquivos


def baixar_arquivo(service, file_id: str, destino: str) -> bool:
    """Baixa o arquivo do Drive para o caminho local. Retorna True/False."""
    try:
        from googleapiclient.http import MediaIoBaseDownload
        request = service.files().get_media(fileId=file_id)
        with open(destino, "wb") as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        return True
    except Exception as e:
        print(f"  Falha ao baixar do Drive: {e}", file=sys.stderr)
        return False


def baixar_manuais(subpasta: str, dir_destino: str,
                   prefixo: str = "manual_") -> list[str]:
    """Baixa todos os arquivos `manual_*` da subpasta no Drive para `dir_destino`.

    Convenção: arquivos com prefixo `manual_` na pasta do CRI são considerados
    upload manual do usuário (escape hatch quando FNet não tem o termo original).
    Se um arquivo de mesmo nome já existir localmente, NÃO sobrescreve.
    Retorna lista de caminhos locais (incluindo arquivos pré-existentes).

    Falhas de autenticação/rede do Drive NÃO são fatais: loga aviso e retorna [].
    """
    try:
        service = obter_servico()
    except Exception as e:
        print(f"  Drive: erro ao inicializar credenciais ({e}). Pulando manuais.",
              file=sys.stderr)
        return []
    base_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "")
    if service is None or not base_id:
        return []
    try:
        folder_id = resolver_subpasta(service, base_id, subpasta, criar=False)
        if folder_id is None:
            return []
        arquivos = listar_arquivos(service, folder_id)
    except Exception as e:
        _avisar_drive_indisponivel(e, contexto="busca de manuais")
        return []
    manuais = [f for f in arquivos if (f["name"] or "").lower().startswith(prefixo)]
    if not manuais:
        return []
    os.makedirs(dir_destino, exist_ok=True)
    resultados = []
    for m in manuais:
        destino = os.path.join(dir_destino, m["name"])
        if os.path.isfile(destino) and os.path.getsize(destino) > 0:
            print(f"  Drive: manual já presente localmente: {m['name']}", file=sys.stderr)
            resultados.append(destino)
            continue
        print(f"  Drive: baixando manual {m['name']}...", file=sys.stderr)
        if baixar_arquivo(service, m["id"], destino):
            resultados.append(destino)
    return resultados


def _avisar_drive_indisponivel(erro: Exception, contexto: str) -> None:
    """Imprime aviso quando o Drive falha por auth ou rede."""
    nome_erro = type(erro).__name__
    msg = str(erro)
    if "invalid_grant" in msg or nome_erro == "RefreshError":
        print(f"  Drive: refresh token inválido/expirado ({contexto}). "
              f"Regere com 'python get_drive_token.py' e atualize o secret "
              f"GOOGLE_REFRESH_TOKEN. Seguindo sem Drive.", file=sys.stderr)
    else:
        print(f"  Drive: falha em {contexto} ({nome_erro}: {msg}). "
              f"Seguindo sem Drive.", file=sys.stderr)


def upload(caminhos: list[str], subpasta: Optional[str] = None,
           skip_existing: bool = False,
           replace_existing: bool = False) -> list[str]:
    """Upload de arquivos para Drive.

    skip_existing: pula arquivos cujo nome já existe na pasta destino.
    replace_existing: atualiza conteúdo do arquivo existente em vez de criar duplicata.
    Padrão (ambos False): cria novo (pode gerar duplicatas — comportamento legado).
    """
    try:
        service = obter_servico()
    except Exception as e:
        _avisar_drive_indisponivel(e, contexto="inicialização do upload")
        return []
    base_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "")
    if service is None or not base_id:
        print("Credenciais OAuth ou GOOGLE_DRIVE_FOLDER_ID não configurados. "
              "Pulando upload.", flush=True)
        return []

    try:
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        print("googleapiclient não instalado.", flush=True)
        return []

    try:
        destino_id = resolver_subpasta(service, base_id, subpasta, criar=True)
        existentes: dict[str, str] = {}
        if skip_existing or replace_existing:
            existentes = {f["name"]: f["id"]
                          for f in listar_arquivos(service, destino_id)}
    except Exception as e:
        _avisar_drive_indisponivel(e, contexto="resolução de subpasta")
        return []

    links = []
    for caminho in caminhos:
        if not os.path.isfile(caminho):
            print(f"  Aviso: arquivo não encontrado: {caminho}")
            continue
        nome = os.path.basename(caminho)
        existing_id = existentes.get(nome)

        if existing_id and skip_existing:
            print(f"  Já existe no Drive (skip): {nome}", flush=True)
            continue

        media = MediaFileUpload(caminho, resumable=True)
        try:
            if existing_id and replace_existing:
                result = service.files().update(
                    fileId=existing_id,
                    media_body=media,
                    fields="id,webViewLink",
                ).execute()
                acao = "Atualizado"
            else:
                result = service.files().create(
                    body={"name": nome, "parents": [destino_id]},
                    media_body=media,
                    fields="id,webViewLink",
                ).execute()
                acao = "Enviado"
        except HttpError as e:
            print(f"  Falha ao enviar {nome}: {e}")
            continue
        link = result.get("webViewLink", "")
        print(f"  {acao}: {nome} -> {link}", flush=True)
        links.append(link)
    return links
