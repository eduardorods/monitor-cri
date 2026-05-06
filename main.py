import argparse
import json
import sys

from cri_monitor import B3Client


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Consulta dados públicos de CRI na API da B3.",
    )
    parser.add_argument("--codigo-if",
                        help="Código IF do CRI (ex.: 19F0076447).")
    parser.add_argument("--cnpj-securitizadora",
                        help="CNPJ da securitizadora (só dígitos).")
    parser.add_argument("--sem-documentos", action="store_true",
                        help="Não buscar documentos FNet.")
    parser.add_argument("--saida",
                        help="Arquivo JSON de saída. Se omitido, imprime no stdout.")

    parser.add_argument("--listar-securitizadoras", action="store_true",
                        help="Dump bruto das securitizadoras retornadas pela B3.")
    parser.add_argument("--listar-cris", action="store_true",
                        help="Dump bruto dos CRIs da securitizadora "
                             "(exige --cnpj-securitizadora).")
    parser.add_argument("--limite", type=int, default=0,
                        help="Limite de itens no modo listar (0 = todos).")

    args = parser.parse_args()
    client = B3Client()

    if args.listar_securitizadoras:
        print("Listando securitizadoras (API B3 + lista local)...", file=sys.stderr)
        from cri_monitor.securitizadoras import SECURITIZADORAS_CONHECIDAS
        from cri_monitor.b3 import _merge_securitizadoras
        merged = _merge_securitizadoras(list(client.securitizadoras()), SECURITIZADORAS_CONHECIDAS)
        print(f"{len(merged)} securitizadora(s) no total.", file=sys.stderr)
        return _dump(merged, args.saida)

    if args.listar_cris:
        if not args.cnpj_securitizadora:
            parser.error("--listar-cris exige --cnpj-securitizadora")
        cnpj = _normalizar_cnpj(args.cnpj_securitizadora)
        print(f"Listando CRIs do CNPJ {cnpj}...", file=sys.stderr)
        cris = []
        for cri in client.cris_por_securitizadora(cnpj):
            cris.append(cri)
            if args.limite and len(cris) >= args.limite:
                break
        print(f"{len(cris)} CRI(s) retornado(s).", file=sys.stderr)
        return _dump(cris, args.saida)

    if not args.codigo_if:
        parser.error("informe --codigo-if (ou use --listar-securitizadoras "
                     "/ --listar-cris para debug).")

    cnpj = _normalizar_cnpj(args.cnpj_securitizadora) if args.cnpj_securitizadora else None
    print(f"Buscando CRI {args.codigo_if}...", file=sys.stderr)

    def _progress(idx, total, nome):
        print(f"  [{idx}/{total}] {nome}", file=sys.stderr)

    info = client.buscar_cri(
        codigo_if=args.codigo_if,
        cnpj_securitizadora=cnpj,
        incluir_documentos=not args.sem_documentos,
        on_progress=_progress if not cnpj else None,
    )
    if info is None:
        print(f"CRI {args.codigo_if} não encontrado.", file=sys.stderr)
        return 1
    return _dump(info.to_dict(), args.saida)


def _dump(obj, saida) -> int:
    payload = json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    if saida:
        with open(saida, "w", encoding="utf-8") as f:
            f.write(payload)
        print(f"Resultado salvo em {saida}", file=sys.stderr)
    else:
        print(payload)
    return 0


def _normalizar_cnpj(cnpj: str) -> str:
    return "".join(c for c in cnpj if c.isdigit())


if __name__ == "__main__":
    sys.exit(main())
