"""Lê o relatório do Domínio "Relação de Rubricas/Itens Não Configurados" e
extrai os códigos de rubrica listados — agrupados por Tipo da Integração
(Folha Normal, Rescisão, Provisão, Empresa...) E por Departamento — pra
pré-selecionar cada tratativa (departamento + tipo, configurados na tela) só
com as rubricas que o relatório lista pro SEU próprio departamento/tipo.

O nome de arquivo do exemplo real ("341 - RubricasItens não Configurados.pdf")
tem o código da empresa de exemplo no início, não um número de relatório — o
relatório em si não tem número, é "RELAÇÃO DE RUBRICAS/ITENS NÃO CONFIGURADOS".

O PDF é gerado pelo Domínio numa estrutura hierárquica: Tipo de folha (ex.
"Folha Normal", "Rescisão") -> Departamento (ex. "Departamento: 1003 VENDAS")
-> lista de pares Código/Descrição. Um mesmo relatório pode ter VÁRIOS
departamentos dentro do mesmo Tipo de folha, e a MESMA rubrica pode aparecer
repetida em departamentos diferentes (exemplo real: a rubrica "336" aparece
nos departamentos 1002, 1003 e 1006, todos dentro de "Folha Normal", e de
novo no departamento 1003 de "Rescisão").

Adicionado em 2026-09-14, a partir do exemplo real
"projetos/rubricas-folha/341 - RubricasItens não Configurados.pdf" — esse
exemplo só tem as seções "Folha Normal" e "Rescisão". `_mapear_tipo_integracao()`
reconhece "Provisão"/"Empresa"/"Férias" por palavra-chave, sem um exemplo real
pra confirmar o texto exato dessas seções — conferir com o Robert quando
aparecer um relatório de verdade com elas.

Atualizado em 2026-10-24, a pedido do Robert: "quando subimos um arquivo de
rubricas não configuradas, ele pode possuir vários departamentos, o arquivo
final deve ler a rubrica por departamento, e o histórico [...] deve se
atentar se tiver a mesma rubrica por departamento, o histórico deve ser o
mesmo" — antes, a linha "Departamento: ..." só servia pra pular (os códigos
de departamentos diferentes dentro do mesmo Tipo de folha viravam um único
balde, sem distinção de departamento). Agora
`extrair_itens_por_tipo_e_departamento()` preserva essa granularidade, e
`selecionar_itens_para_departamento()` cruza cada tratativa com o
departamento certo do relatório (streamlit_app.py usa isso nas seções 2 e 3).
A parte do histórico compartilhado quando a mesma rubrica repete entre
departamentos já estava implementada (dominio_export.novo_estado_historico,
2026-09-18) — só dependia de cada tratativa receber as rubricas certas do
SEU departamento, que é o que esta mudança corrige.
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


def _codigo_departamento(linha_departamento):
    """"Departamento: 1002 SERVIÇOS" -> "1002" — só o código, que é o que
    bate com o campo "Departamento" (código gravado no EVENTO/INTEGRA) que o
    Robert configura por tratativa na tela."""
    texto = linha_departamento.split(":", 1)[1].strip() if ":" in linha_departamento else linha_departamento.strip()
    tokens = texto.split()
    return tokens[0] if tokens else ""


def normalizar_codigo_departamento(texto):
    """Primeiro token (ignora nome descritivo depois do código) sem zeros à
    esquerda — pra "1002", "1002 SERVIÇOS" e "01002" baterem como o mesmo
    departamento na hora de cruzar com o relatório."""
    texto = str(texto or "").strip()
    tokens = texto.split()
    primeiro = tokens[0] if tokens else texto
    return primeiro.lstrip("0") or "0"


def extrair_itens_por_secao_e_departamento(arquivo_pdf):
    """Devolve {texto_da_seção: {código_departamento: {código_rubrica: nome}}}
    — a estrutura completa do relatório, SEM perder o departamento de cada
    rubrica (2026-10-24, a pedido do Robert: "ele pode possuir vários
    departamentos, o arquivo final deve ler a rubrica por departamento").
    Antes disso, a linha "Departamento: ..." só era usada pra pular (os
    códigos de seções/departamentos diferentes viravam um único balde por
    Tipo de folha) — uma mesma rubrica em departamentos diferentes não dava
    pra distinguir."""
    linhas = _ler_linhas(arquivo_pdf)

    resultado = {}
    secao_atual = None
    departamento_atual = None
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
                resultado.setdefault(secao_atual, {}).setdefault(departamento_atual, {})[linha] = nome
                i += 2  # pula a descrição junto com o código
                continue
            dentro_bloco = False
            continue  # reprocessa esta linha: "Departamento: ..." ou novo Tipo

        if linha.startswith("Departamento:"):
            departamento_atual = _codigo_departamento(linha)
            i += 1
            continue

        # Linha solta fora de bloco e que não é "Departamento:": é o
        # cabeçalho de uma nova seção (Tipo de folha).
        secao_atual = linha
        departamento_atual = None
        i += 1

    return resultado


def extrair_itens_por_secao(arquivo_pdf):
    """Devolve um dict {texto_da_seção: {código: nome}} — o texto da seção é
    exatamente como aparece no relatório (ex. "Folha Normal", "Rescisão"),
    sem tentar interpretar o que significa (isso é trabalho de
    `_mapear_tipo_integracao`). Preserva o NOME de cada rubrica (não só o
    código) — necessário quando o relatório é usado como a própria lista de
    rubricas a processar, sem a relação de rubricas completa da empresa
    (2026-09-14: "em alguns casos eu não vou ter a relação de rubricas da
    empresa, somente a relação de rubricas não cadastradas"). Achata os
    departamentos (união) — quem precisa da rubrica POR departamento usa
    `extrair_itens_por_secao_e_departamento`."""
    por_secao_e_departamento = extrair_itens_por_secao_e_departamento(arquivo_pdf)
    resultado = {}
    for secao, por_departamento in por_secao_e_departamento.items():
        itens_secao = {}
        for itens in por_departamento.values():
            itens_secao.update(itens)
        resultado[secao] = itens_secao
    return resultado


def extrair_itens_por_tipo_integracao(arquivo_pdf):
    """Devolve {tipo_integracao (1-6): {código: nome}}, juntando todas as
    seções do relatório que mapeiam pro mesmo Tipo da Integração (achatado,
    sem departamento — ver `extrair_itens_por_tipo_e_departamento`)."""
    por_secao = extrair_itens_por_secao(arquivo_pdf)
    por_tipo = {}
    for secao, itens in por_secao.items():
        tipo_integracao = _mapear_tipo_integracao(secao)
        por_tipo.setdefault(tipo_integracao, {}).update(itens)
    return por_tipo


def extrair_itens_por_tipo_e_departamento(arquivo_pdf):
    """Devolve {tipo_integracao (1-6): {código_departamento: {código_rubrica:
    nome}}} — junta seções do mesmo Tipo da Integração, mas mantém os
    departamentos separados dentro de cada tipo. É o que
    `selecionar_itens_para_departamento` usa pra cruzar cada tratativa
    (departamento + Tipo da Integração configurados na tela) com as rubricas
    certas do relatório."""
    por_secao_e_departamento = extrair_itens_por_secao_e_departamento(arquivo_pdf)
    por_tipo_e_departamento = {}
    for secao, por_departamento in por_secao_e_departamento.items():
        tipo_integracao = _mapear_tipo_integracao(secao)
        destino = por_tipo_e_departamento.setdefault(tipo_integracao, {})
        for departamento, itens in por_departamento.items():
            destino.setdefault(departamento, {}).update(itens)
    return por_tipo_e_departamento


def selecionar_itens_para_departamento(itens_por_tipo_e_departamento, tipo_integracao, codigo_departamento):
    """Cruza uma tratativa (Tipo da Integração + código de departamento,
    configurados na tela) com a estrutura do relatório. Devolve (itens,
    bateu_exato):
    - Se o departamento configurado bate (por `normalizar_codigo_departamento`)
      com um departamento do relatório PARA ESSE TIPO: devolve só os itens
      daquele departamento, bateu_exato=True.
    - Senão (departamento não encontrado, ou relatório sem granularidade de
      departamento pra esse tipo): devolve a UNIÃO de todos os departamentos
      daquele tipo (comportamento de antes de 2026-10-24), bateu_exato=False
      — quem chama decide se avisa o usuário."""
    por_departamento = itens_por_tipo_e_departamento.get(tipo_integracao, {})
    if not por_departamento:
        return {}, False

    alvo = normalizar_codigo_departamento(codigo_departamento)
    for departamento, itens in por_departamento.items():
        if departamento is not None and normalizar_codigo_departamento(departamento) == alvo:
            return dict(itens), True

    uniao = {}
    for itens in por_departamento.values():
        uniao.update(itens)
    return uniao, False


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
