import argparse
import json
import sys

from cri_monitor import B3Client


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Consulta dados públicos de um CRI na API da B3.",
    )
    parser.add_argument(
        "--codigo-if",
        required=True,
        help="Código IF do CRI (ex.: 19F0076447)",
    )
    parser.add_argument(
        "--cnpj-securitizadora",
        help="CNPJ da securitizadora (apenas dígitos). "
             "Se informado, acelera muito a busca.",
    )
    parser.add_argument(
        "--sem-documentos",
        action="store_true",
        help="Não buscar a lista de documentos do CRI.",
    )
    parser.add_argument(
        "--saida",
        help="Caminho do arquivo JSON de saída. "
             "Se omitido, imprime no stdout.",
    )
    args = parser.parse_args()

    cnpj = _normalizar_cnpj(args.cnpj_securitizadora) if args.cnpj_securitizadora else None

    client = B3Client()
    print(f"Buscando CRI {args.codigo_if}...", file=sys.stderr)
    info = client.buscar_cri(
        codigo_if=args.codigo_if,
        cnpj_securitizadora=cnpj,
        incluir_documentos=not args.sem_documentos,
    )

    if info is None:
        print(f"CRI {args.codigo_if} não encontrado.", file=sys.stderr)
        return 1

    payload = json.dumps(info.to_dict(), ensure_ascii=False, indent=2, default=str)

    if args.saida:
        with open(args.saida, "w", encoding="utf-8") as f:
            f.write(payload)
        print(f"Resultado salvo em {args.saida}", file=sys.stderr)
    else:
        print(payload)

    return 0


def _normalizar_cnpj(cnpj: str) -> str:
    return "".join(c for c in cnpj if c.isdigit())


if __name__ == "__main__":
    sys.exit(main())
