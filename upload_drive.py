"""CLI para enviar arquivos para o Google Drive.

Uso:
    python upload_drive.py <caminho1> [<caminho2> ...] --subpasta CRIs/22I1560033
    python upload_drive.py --skip-existing ...    # pula arquivos com mesmo nome
    python upload_drive.py --replace-existing ... # atualiza em vez de duplicar

Variáveis de ambiente obrigatórias:
    GOOGLE_DRIVE_FOLDER_ID  — ID da pasta raiz no Drive
    GOOGLE_CLIENT_ID        — OAuth 2.0 Client ID
    GOOGLE_CLIENT_SECRET    — OAuth 2.0 Client Secret
    GOOGLE_REFRESH_TOKEN    — OAuth 2.0 Refresh Token (gerado por get_drive_token.py)
"""
import argparse

from cri_monitor.drive import upload


def _parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("arquivos", nargs="+", help="Arquivos a enviar")
    p.add_argument("--subpasta", default=None,
                   help="Caminho de subpastas (ex.: 'CRIs/22I1560033'). Cria se não existir.")
    p.add_argument("--skip-existing", action="store_true",
                   help="Pula arquivos cujo nome já existe na pasta destino.")
    p.add_argument("--replace-existing", action="store_true",
                   help="Atualiza conteúdo de arquivos com mesmo nome (sem criar duplicata).")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    upload(args.arquivos, args.subpasta,
           skip_existing=args.skip_existing,
           replace_existing=args.replace_existing)
