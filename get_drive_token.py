"""
Gera um refresh token OAuth para o Google Drive.
Execute UMA VEZ localmente antes de configurar os secrets do GitHub.

Pré-requisito:
    pip install google-auth-oauthlib

Uso:
    python get_drive_token.py --client-id SEU_CLIENT_ID --client-secret SEU_CLIENT_SECRET

Como obter client-id e client-secret:
    1. Console GCP -> APIs & Services -> Credentials
    2. Create Credentials -> OAuth 2.0 Client IDs -> Desktop app
    3. Baixe o JSON ou copie os valores
"""
import argparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-id", required=True, help="OAuth Client ID")
    parser.add_argument("--client-secret", required=True, help="OAuth Client Secret")
    args = parser.parse_args()

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Execute: pip install google-auth-oauthlib")
        raise SystemExit(1)

    client_config = {
        "installed": {
            "client_id": args.client_id,
            "client_secret": args.client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(
        client_config,
        scopes=["https://www.googleapis.com/auth/drive.file"],
    )
    creds = flow.run_local_server(port=0)

    print("\n=== Copie estes 3 valores para os secrets do GitHub ===\n")
    print(f"GOOGLE_CLIENT_ID={args.client_id}")
    print(f"GOOGLE_CLIENT_SECRET={args.client_secret}")
    print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
    print("\n(O GOOGLE_CREDENTIALS e WIF_PROVIDER não são mais necessários)")


if __name__ == "__main__":
    main()
