"""Lê o relatório do Domínio "Relação de Rubricas/Itens Não Configurados" e
extrai os códigos de rubrica listados — agrupados por Tipo da Integração
(Folha Normal, Rescisão, Provisão, Empresa...) — pra pré-selecionar cada
departamento só com as rubricas do SEU próprio tipo.

O nome de arquivo do exemplo real ("341 - RubricasItens não Configurados.pdf")
tem o código da empresa de exemplo no início, não um número de relatório — o
relatório em si não tem número, é "RELAÇÃO DE RUBRICAS/ITENS NÃO CONFIGURADOS".

O PDF é gerado pelo Domínio numa estrutura hierárquica: Tipo de folha (ex.
"Folha Normal", "Rescisão") -> Departamento (ex. "Departamento: 1003 VENDAS")
-> lista de pares Código/Descrição.

Adicionado em 2026-09-14, a partir do exemplo real
"projetos/rubricas-folha/341 - RubricasItens não Configurados.pdf" — esse
exemplo só tem as seções "Folha Normal" e "Rescisão". `_mapear_tipo_integracao()`
reconhece "Provisão"/"Empresa"/"Férias" por palavra-chave, sem um exemplo real
pra confirmar o texto exato dessas seções — conferir com o Robert quando
aparecer um relatório de verdade com elas.
"""

import fitz

# Rótulos que aparecem antes do primeiro "Departamento:" de cada seção do
# relatório (ex. "Folha Normal", "Rescisão") -> Tipo da Integração (1-6, mesmo
# código usado em bhub_model.TIPO_INTEGRACAO_LABELS). Nenhuma seção "Tipo 3"
# (Férias) tem aba própria no modelo BHub (ver bhub_model.py) — mapeada aqui
# só por completude, caso apareça no relatório.
_PALAVRAS_CHAVE_TIPO = [
    (4, ("RESCIS",)),
    (6, ("PROVIS", "13")),
    (6, ("PROVIS", "DÉCIMO")),
    (6, ("PROVIS", "DECIMO")),
    (5, ("PROVIS",)),  # provisão sem "13"/"décimo" no texto -> assume férias
    (2, ("EMPRESA",)),
    (3, ("FÉRIAS",)),
    (3, ("FERIAS",)),
]


def _mapear_tipo_integracao(tipo_bruto):
    """Classifica o texto de uma seção do relatório (ex. "Folha Normal") num
    Tipo da Integração 1-6. Sem nenhuma palavra-chave reconhecida (inclusive
    "Folha Normal" em si), cai no padrão — tipo 1 (Folha mensal)."""
    if not tipo_bruto:
        return 1
    texto = tipo_bruto.upper()
    for tipo_integracao, palavras in _PALAVRAS_CHAVE_TIPO:
        if all(palavra in texto for palavra in palavras):
            return tipo_integracao
    return 1


def _ler_linhas(arquivo_pdf):
    if hasattr(arquivo_pdf, "read"):
        documento = fitz.open(stream=arquivo_pdf.read(), filetype="pdf")
    else:
        documento = fitz.open(arquivo_pdf)
    linhas = []
    for pagina in documento:
        linhas.extend(
            linha.strip() for linha in pagina.get_text().splitlines() if linha.strip()
        )
    return linhas


def extrair_itens_por_secao(arquivo_pdf):
    """Devolve um dict {texto_da_seção: {código: nome}} — o texto da seção é
    exatamente como aparece no relatório (ex. "Folha Normal", "Rescisão"),
    sem tentar interpretar o que significa (isso é trabalho de
    `_mapear_tipo_integracao`). Preserva o NOME de cada rubrica (não só o
    código) — necessário quando o relatório é usado como a própria lista de
    rubricas a processar, sem a relação de rubricas completa da empresa
    (2026-09-14: "em alguns casos eu não vou ter a relação de rubricas da
    empresa, somente a relação de rubricas não cadastradas")."""
    linhas = _ler_linhas(arquivo_pdf)

    resultado = {}
    secao_atual = None
    dentro_bloco = False
    cabecalho_ok = False
    i = 0
    while i < len(linhas):
        linha = linhas[i]

        if not cabecalho_ok:
            # Pula o cabeçalho fixo do relatório (título, página, data/hora,
            # empresa) até a linha seguinte a "Empresa:", que é o código+nome
            # da empresa — depois disso começa o conteúdo de verdade.
            if linha == "Empresa:":
                i += 2
                cabecalho_ok = True
                continue
            i += 1
            continue

        if linha == "Código" and i + 1 < len(linhas) and linhas[i + 1] == "Descrição":
            dentro_bloco = True
            i += 2
            continue

        if dentro_bloco:
            if linha.isdigit():
                nome = linhas[i + 1] if i + 1 < len(linhas) else ""
                resultado.setdefault(secao_atual, {})[linha] = nome
                i += 2  # pula a descrição junto com o código
                continue
            dentro_bloco = False
            continue  # reprocessa esta linha: "Departamento: ..." ou novo Tipo

        if linha.startswith("Departamento:"):
            i += 1
            continue

        # Linha solta fora de bloco e que não é "Departamento:": é o
        # cabeçalho de uma nova seção (Tipo de folha).
        secao_atual = linha
        i += 1

    return resultado


def extrair_itens_por_tipo_integracao(arquivo_pdf):
    """Devolve {tipo_integracao (1-6): {código: nome}}, juntando todas as
    seções do relatório que mapeiam pro mesmo Tipo da Integração."""
    por_secao = extrair_itens_por_secao(arquivo_pdf)
    por_tipo = {}
    for secao, itens in por_secao.items():
        tipo_integracao = _mapear_tipo_integracao(secao)
        por_tipo.setdefault(tipo_integracao, {}).update(itens)
    return por_tipo


def extrair_codigos_por_secao(arquivo_pdf):
    """Como `extrair_itens_por_secao`, mas só os códigos (sem nome) — pra
    quem só precisa cruzar com uma relação de rubricas já carregada."""
    return {secao: set(itens) for secao, itens in extrair_itens_por_secao(arquivo_pdf).items()}


def extrair_codigos_por_tipo_integracao(arquivo_pdf):
    """Como `extrair_itens_por_tipo_integracao`, mas só os códigos."""
    return {tipo: set(itens) for tipo, itens in extrair_itens_por_tipo_integracao(arquivo_pdf).items()}


def extrair_codigos(arquivo_pdf):
    """União de todos os códigos do relatório, sem distinguir seção/tipo —
    mantido pra compatibilidade com quem só quer a lista completa."""
    codigos = set()
    for grupo in extrair_codigos_por_secao(arquivo_pdf).values():
        codigos.update(grupo)
    return codigos
