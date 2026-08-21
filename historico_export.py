"""Gera o cadastro de históricos padrões (layout "Modelo Históricos.txt").

    |0000|<CNPJ da empresa>|
    |0220|<número do histórico>|<descrição>|

O número do histórico é o mesmo gerado em dominio_export.gerar_arquivos_dominio().
Todos os templates de descrição abaixo foram confirmados pelo Robert (notas.md
2026-07-15b/g/h, 2026-07-16e) — o sufixo "#N" é obrigatório em TODOS eles (é o
comando do Domínio que puxa a competência do lançamento).

Reconstruído em 2026-08-19 a partir de notas.md.
"""

# Provisão de férias/13º e o caso "empresa" (impostos/encargos) são identificados
# pelo TIPO da rubrica BHub, não pela natureza — férias e 13º compartilham a mesma
# natureza "-" que também é usada pelo tipo "empresa".
TEMPLATES_POR_TIPO = {
    "provisao_ferias": "PROVISÃO FÉRIAS REF. RUBRICA {numero} - {descricao} #N",
    "provisao_13": "PROVISÃO 13º REFERENTE RUBRICA {numero} - {descricao} #N",
    "empresa": "VALOR REF. RUBRICA {descricao} #N",
}

TEMPLATES_POR_NATUREZA = {
    "P": "PROVENTOS REF. RUBRICA {numero} - {descricao} #N",
    "D": "DESCONTO REF. RUBRICA {numero} - {descricao} #N",
    "I": "{numero} - {descricao} #N",
    "ID": "{numero} - {descricao} #N",
}


def _fmt_numero(valor):
    texto = str(valor).strip()
    return texto[:-2] if texto.endswith(".0") else texto


def _escolher_template(tipo_rubrica_bhub, natureza_rubrica):
    """Devolve (template, confirmado). confirmado=False sinaliza um template
    hipotético (nenhum caso confirmado deveria cair aqui hoje, mas fica como
    salvaguarda para tipos/naturezas novos que apareçam no futuro)."""
    if tipo_rubrica_bhub in TEMPLATES_POR_TIPO:
        return TEMPLATES_POR_TIPO[tipo_rubrica_bhub], True
    if natureza_rubrica in TEMPLATES_POR_NATUREZA:
        return TEMPLATES_POR_NATUREZA[natureza_rubrica], True
    return "{numero} - {descricao} #N", False


def gerar_arquivo_historicos(linhas, cnpj_empresa):
    """Devolve (texto_do_arquivo, numeros_com_template_nao_confirmado)."""
    corpo = [f"|0000|{cnpj_empresa}|"]
    avisos = []

    for linha in linhas:
        template, confirmado = _escolher_template(linha.tipo_rubrica_bhub, linha.natureza_rubrica)
        descricao = template.format(
            numero=_fmt_numero(linha.numero_rubrica_bhub),
            descricao=linha.descricao,
        )
        corpo.append(f"|0220|{linha.numero_historico}|{descricao}|")
        if not confirmado:
            avisos.append(linha.numero_historico)

    return "\n".join(corpo), avisos
