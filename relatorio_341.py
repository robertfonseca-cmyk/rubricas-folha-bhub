"""Lê o relatório do Domínio "Relação de Rubricas/Itens Não Configurados" e
extrai os códigos de rubrica listados, pra pré-selecionar essas rubricas na
tela de seleção (em vez de marcar uma por uma).

O nome de arquivo do exemplo real ("341 - RubricasItens não Configurados.pdf")
tem o código da empresa de exemplo no início, não um número de relatório — o
relatório em si não tem número, é "RELAÇÃO DE RUBRICAS/ITENS NÃO CONFIGURADOS".

O PDF é gerado pelo Domínio numa estrutura hierárquica: Tipo de folha (ex.
"Folha Normal", "Rescisão") -> Departamento (ex. "Departamento: 1003 VENDAS")
-> lista de pares Código/Descrição. Esta função ignora essa hierarquia de
propósito e devolve só a UNIÃO de todos os códigos do relatório inteiro — o
Robert pediu pra selecionar "as rubricas que preciso contabilizar", sem pedir
separação por departamento/tipo (se precisar disso no futuro, dá pra estender
mantendo o agrupamento em vez de descartar).

Adicionado em 2026-09-14, a partir do exemplo real
"projetos/rubricas-folha/341 - RubricasItens não Configurados.pdf".
"""

import fitz


def extrair_codigos(arquivo_pdf):
    """`arquivo_pdf`: caminho (str/Path) ou arquivo enviado pelo Streamlit
    (UploadedFile, arquivo-like). Devolve um `set` de códigos de rubrica
    (string) encontrados em qualquer bloco Código/Descrição do relatório."""
    if hasattr(arquivo_pdf, "read"):
        documento = fitz.open(stream=arquivo_pdf.read(), filetype="pdf")
    else:
        documento = fitz.open(arquivo_pdf)

    linhas = []
    for pagina in documento:
        linhas.extend(
            linha.strip() for linha in pagina.get_text().splitlines() if linha.strip()
        )

    codigos = set()
    dentro_bloco = False
    i = 0
    while i < len(linhas):
        linha = linhas[i]
        if linha == "Código" and i + 1 < len(linhas) and linhas[i + 1] == "Descrição":
            dentro_bloco = True
            i += 2
            continue
        if dentro_bloco:
            if linha.isdigit():
                codigos.add(linha)
                i += 2  # pula a linha de descrição junto com o código
                continue
            dentro_bloco = False
            continue  # reprocessa esta linha: é "Departamento: ..." ou um novo tipo
        i += 1

    return codigos
