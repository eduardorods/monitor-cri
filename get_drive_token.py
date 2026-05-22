"""
Gera um refresh token OAuth para o Google Drive.
Execute UMA VEZ no Cloud Shell ou localmente.

Não requer dependências extras — usa apenas a biblioteca padrão do Python.

Uso:
    python get_drive_token.py --client-id SEU_CLIENT_ID --client-secret SEU_CLIENT_SECRET
"""
import argparse
import json
import secrets
import urllib.parse
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-id", required=True, help="OAuth Client ID")
    parser.add_argument("--client-secret", required=True, help="OAuth Client Secret")
    args = parser.parse_args()

    state = secrets.token_urlsafe(16)
    redirect_uri = "http://localhost"

    auth_params = {
        "client_id": args.client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/drive.file",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    auth_url = "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode(auth_params)

    print("\n1. Abra este link no navegador:\n")
    print(auth_url)
    print("\n2. Faça login e autorize o acesso ao Drive.")
    print("3. Você será redirecionado para uma página de erro (localhost) — isso é NORMAL.")
    print("4. Copie a URL completa da barra de endereços do navegador e cole abaixo.\n")

    redirect_url = input("Cole aqui a URL completa da barra de endereços: ").strip()

    parsed = urllib.parse.urlparse(redirect_url)
    params = urllib.parse.parse_qs(parsed.query)
    code = params.get("code", [None])[0]

    if not code:
        print("\nErro: parâmetro 'code' não encontrado na URL. Tente novamente.")
        raise SystemExit(1)

    token_data = urllib.parse.urlencode({
        "code": code,
        "client_id": args.client_id,
        "client_secret": args.client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode()

    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            token_response = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"\nErro ao trocar o código por token: {e.code} {body}")
        raise SystemExit(1)

    refresh_token = token_response.get("refresh_token")
    if not refresh_token:
        print("\nErro: refresh_token não retornado. Certifique-se de ter usado 'prompt=consent'.")
        raise SystemExit(1)

    print("\n=== Copie estes 3 valores para os secrets do GitHub ===\n")
    print(f"GOOGLE_CLIENT_ID={args.client_id}")
    print(f"GOOGLE_CLIENT_SECRET={args.client_secret}")
    print(f"GOOGLE_REFRESH_TOKEN={refresh_token}")
    print("\n(Não precisa mais de GOOGLE_CREDENTIALS, WIF_PROVIDER ou SERVICE_ACCOUNT)")


if __name__ == "__main__":
    main()
