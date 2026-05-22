import argparse
import json
import os
import sys
from dataclasses import asdict
from typing import Optional

from cri_monitor import B3Client
from cri_monitor.fnet import baixar_documento
from cri_monitor.pdf_parser import ResumoOperacao, analisar, extrair_texto


CATEGORIAS_BAIXAR_DEFAULT = (
    "termo_securitizacao",
    "aditamento",
    "ata_assembleia",
    "relatorio_agente_fiduciario",
)


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
                        help="Arquivo de saída (.json ou .xlsx). Se omitido, imprime no stdout.")
    parser.add_argument("--baixar-pdfs", metavar="DIR",
                        help="Diretório onde salvar os PDFs baixados (e parsear o Termo).")

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

    resumo: Optional[ResumoOperacao] = None
    pdfs_baixados: list[str] = []

    if args.baixar_pdfs and info.documentos:
        pdfs_baixados, resumo = _baixar_e_analisar(info, args.baixar_pdfs)
        _preencher_lacunas(info, resumo)

    payload = info.to_dict()
    if resumo is not None:
        payload["resumo_operacao"] = asdict(resumo)
    if pdfs_baixados:
        payload["pdfs_baixados"] = pdfs_baixados

    return _dump(payload, args.saida)


def _baixar_e_analisar(info, dir_destino: str):
    """Baixa PDFs das categorias relevantes e parseia o Termo de Securitização."""
    alvo_dir = os.path.join(dir_destino, info.codigo_if or "cri")
    print(f"Baixando PDFs para {alvo_dir}...", file=sys.stderr)

    pdfs_baixados: list[str] = []
    caminho_termo: Optional[str] = None
    for i, doc in enumerate(info.documentos, 1):
        if doc.categoria_normalizada not in CATEGORIAS_BAIXAR_DEFAULT:
            continue
        if not doc.url:
            continue
        nome_base = f"{i:03d}_{(doc.categoria_normalizada or 'doc')}_{(doc.nome or 'doc')}"
        caminho = baixar_documento(doc.url, alvo_dir, nome_base)
        if caminho:
            print(f"  Baixado: {os.path.basename(caminho)}", file=sys.stderr)
            pdfs_baixados.append(caminho)
            if doc.categoria_normalizada == "termo_securitizacao" and not caminho_termo:
                caminho_termo = caminho

    resumo: Optional[ResumoOperacao] = None
    if caminho_termo:
        print(f"Analisando Termo de Securitização: {os.path.basename(caminho_termo)}", file=sys.stderr)
        texto = extrair_texto(caminho_termo)
        resumo = analisar(texto)

    return pdfs_baixados, resumo


def _preencher_lacunas(info, resumo: Optional[ResumoOperacao]) -> None:
    if not resumo:
        return
    if not info.devedor and resumo.devedor:
        info.devedor = resumo.devedor
    if not info.data_emissao and resumo.data_emissao:
        info.data_emissao = resumo.data_emissao
    if not info.data_vencimento and resumo.data_vencimento:
        info.data_vencimento = resumo.data_vencimento
    if not info.remuneracao and resumo.taxa_remuneracao:
        info.remuneracao = resumo.taxa_remuneracao


def _dump(obj, saida) -> int:
    if saida and saida.lower().endswith(".xlsx"):
        _dump_excel(obj, saida)
        print(f"Resultado salvo em {saida}", file=sys.stderr)
        return 0
    payload = json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    if saida:
        with open(saida, "w", encoding="utf-8") as f:
            f.write(payload)
        print(f"Resultado salvo em {saida}", file=sys.stderr)
    else:
        print(payload)
    return 0


def _dump_excel(obj, path: str) -> None:
    import openpyxl
    from openpyxl.styles import Font

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    if isinstance(obj, dict):
        # Aba Resumo
        ws = wb.create_sheet("Resumo")
        campos = [
            ("Código IF",          "codigo_if"),
            ("ISIN",               "isin"),
            ("Securitizadora",     "nome_securitizadora"),
            ("CNPJ Securitizadora","cnpj_securitizadora"),
            ("Agente Fiduciário",  "agente_fiduciario"),
            ("Emissão",            "emissao"),
            ("Série",              "serie"),
            ("Data de Emissão",    "data_emissao"),
            ("Data de Vencimento", "data_vencimento"),
            ("Remuneração",        "remuneracao"),
            ("Devedor",            "devedor"),
            ("Descrição",          "descricao"),
            ("Fase",               "fase"),
        ]
        for i, (label, key) in enumerate(campos, 1):
            ws.cell(row=i, column=1, value=label).font = Font(bold=True)
            ws.cell(row=i, column=2, value=obj.get(key))
        ws.column_dimensions["A"].width = 25
        ws.column_dimensions["B"].width = 55

        # Aba Resumo da Operação (parsing do Termo de Securitização)
        resumo = obj.get("resumo_operacao")
        if resumo:
            wo = wb.create_sheet("Resumo da Operação")
            ordem = [
                ("Devedor",            "devedor"),
                ("CNPJ do Devedor",    "cnpj_devedor"),
                ("Valor Total",        "valor_total"),
                ("Data de Emissão",    "data_emissao"),
                ("Data de Vencimento", "data_vencimento"),
                ("Taxa / Remuneração", "taxa_remuneracao"),
                ("Índice",             "indice_atualizacao"),
                ("Coordenador Líder",  "coordenador_lider"),
                ("Agente Fiduciário",  "agente_fiduciario"),
                ("Lastro",             "lastro"),
            ]
            for i, (label, key) in enumerate(ordem, 1):
                wo.cell(row=i, column=1, value=label).font = Font(bold=True)
                wo.cell(row=i, column=2, value=resumo.get(key))
            garantias = resumo.get("garantias") or []
            wo.cell(row=len(ordem) + 1, column=1, value="Garantias").font = Font(bold=True)
            wo.cell(row=len(ordem) + 1, column=2, value=", ".join(garantias) if garantias else None)
            wo.column_dimensions["A"].width = 25
            wo.column_dimensions["B"].width = 70

        # Aba Documentos
        docs = obj.get("documentos") or []
        if docs:
            wd = wb.create_sheet("Documentos")
            headers = ["Nome", "Tipo", "Categoria", "Categoria Norm.",
                       "Data Entrega", "Data Referência", "URL"]
            keys    = ["nome", "tipo", "categoria", "categoria_normalizada",
                       "data_entrega", "data_referencia", "url"]
            for col, h in enumerate(headers, 1):
                wd.cell(row=1, column=col, value=h).font = Font(bold=True)
            for row, doc in enumerate(docs, 2):
                for col, k in enumerate(keys, 1):
                    wd.cell(row=row, column=col, value=doc.get(k))
            for col in range(1, len(headers) + 1):
                wd.column_dimensions[openpyxl.utils.get_column_letter(col)].width = 30

    elif isinstance(obj, list) and obj:
        ws = wb.create_sheet("Dados")
        headers = list(obj[0].keys())
        for col, h in enumerate(headers, 1):
            ws.cell(row=1, column=col, value=h).font = Font(bold=True)
        for row, item in enumerate(obj, 2):
            for col, k in enumerate(headers, 1):
                ws.cell(row=row, column=col, value=str(item.get(k, "") or ""))

    wb.save(path)


def _normalizar_cnpj(cnpj: str) -> str:
    return "".join(c for c in cnpj if c.isdigit())


if __name__ == "__main__":
    sys.exit(main())
