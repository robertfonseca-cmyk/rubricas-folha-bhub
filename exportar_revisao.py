"""Exporta a tabela de revisão (etapa 3 da tela) em CSV, XLSX ou PDF — só para
consulta/compartilhamento; o arquivo que vai pro Domínio é gerado à parte por
dominio_export.py / historico_export.py.

Reconstruído em 2026-08-19 a partir de notas.md.
"""

import io

import pandas as pd

COLUNAS_PDF = [
    "situacao",
    "numero_rubrica_empresa",
    "nome_rubrica_empresa",
    "conta_debito_empresa",
    "conta_credito_empresa",
    "aprovado",
]


def gerar_csv(df):
    return df.to_csv(index=False).encode("utf-8-sig")


def gerar_xlsx(df):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Revisão")
    return buffer.getvalue()


def gerar_pdf(df):
    # Import local: reportlab só é necessário se o usuário pedir o PDF.
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

    colunas = [c for c in COLUNAS_PDF if c in df.columns]
    dados = [colunas] + df[colunas].astype(str).values.tolist()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
    tabela = Table(dados, repeatRows=1)
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F1727")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
    ]))
    doc.build([tabela])
    return buffer.getvalue()


FORMATOS = {
    # Excel primeiro (não mais CSV) — é o formato padrão pedido pelo Robert
    # em 2026-09-10; a ordem aqui decide a opção padrão do selectbox na tela.
    "Excel (XLSX)": {
        "extensao": "xlsx",
        "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "gerador": gerar_xlsx,
    },
    "CSV": {
        "extensao": "csv",
        "mime": "text/csv",
        "gerador": gerar_csv,
    },
    "PDF": {
        "extensao": "pdf",
        "mime": "application/pdf",
        "gerador": gerar_pdf,
    },
}
