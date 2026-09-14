"""Roda o pipeline ponta a ponta (modelo BHub + arquivos da empresa -> tabela de
revisão). Usado tanto pelo streamlit_app.py quanto como script standalone.

Reconstruído em 2026-08-19 a partir de notas.md.
"""

import argparse

import pandas as pd

import bhub_model
import empresa_loader
import matching
from dominio_export import LinhaResolvida

CAMINHO_PARAMETRIZACAO = "dados_bhub/[Base 141935 - Padrão 100.000] Parametrização contábil de rubricas.xlsx"
CAMINHO_PLANO_CONTAS_BHUB = "dados_bhub/Plano de contas padrão - PJ em Geral.xlsx"


def _codigo_da_conta_empresa(valor):
    """Extrai o código de um campo "código - nome" (ou só o código puro)."""
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto or texto.lower() == "none":
        return None
    return texto.split(" - ", 1)[0].strip()


def _formatar_conta(conta_empresa):
    if conta_empresa is None:
        return None
    return f"{conta_empresa.codigo} - {conta_empresa.nome}"


def montar_tabela_revisao(modelo, contas_empresa, rubricas_empresa, natureza_empresa, tipo_integracao, progress_callback=None):
    """progress_callback(i, total), se informado, é chamado periodicamente
    (a cada ~0,5% do total) para alimentar uma barra de progresso na UI."""
    tipo_rubrica_bhub = bhub_model.TIPO_INTEGRACAO.get(tipo_integracao, "folha")
    rubricas_bhub_do_tipo = modelo.rubricas_por_tipo(tipo_rubrica_bhub)

    # Índices construídos uma vez só (não a cada rubrica) — e cache de conta por
    # código BHub, já que o mesmo código de contrapartida se repete em muitas
    # rubricas. Sem isso, o matching fuzzy de uma relação de milhares de rubricas
    # fica impraticavelmente lento (uma rodada real chegou a passar de 2 minutos).
    indice_rubricas_bhub = matching.construir_indice_rubricas_bhub(rubricas_bhub_do_tipo)
    indice_contas_empresa = matching.construir_indice_contas_empresa(contas_empresa)
    cache_contas = {}

    def _match_conta_cacheado(codigo_conta_bhub):
        if codigo_conta_bhub not in cache_contas:
            cache_contas[codigo_conta_bhub] = matching.match_conta(
                codigo_conta_bhub, modelo.plano_contas, indice_contas_empresa
            )
        return cache_contas[codigo_conta_bhub]

    total = len(rubricas_empresa)
    passo_aviso = max(1, total // 200)

    linhas = []
    for i, rubrica_empresa in enumerate(rubricas_empresa, start=1):
        rubrica_bhub, metodo_match, confianca_match = matching.match_rubrica(
            rubrica_empresa, indice_rubricas_bhub
        )

        conta_debito_bhub_cod = conta_credito_bhub_cod = None
        if rubrica_bhub is not None and natureza_empresa in rubrica_bhub.contas:
            conta_debito_bhub_cod, conta_credito_bhub_cod = rubrica_bhub.contas[natureza_empresa]

        conta_debito_emp = conta_credito_emp = None
        confianca_debito = confianca_credito = 0.0
        if conta_debito_bhub_cod:
            conta_debito_emp, confianca_debito = _match_conta_cacheado(conta_debito_bhub_cod)
        if conta_credito_bhub_cod:
            conta_credito_emp, confianca_credito = _match_conta_cacheado(conta_credito_bhub_cod)

        situacao = matching.classificar_situacao(
            rubrica_bhub, metodo_match, confianca_match, natureza_empresa,
            conta_debito_emp, confianca_debito, conta_credito_emp, confianca_credito,
        )

        conta_debito_bhub = modelo.plano_contas.get(conta_debito_bhub_cod)
        conta_credito_bhub = modelo.plano_contas.get(conta_credito_bhub_cod)

        linhas.append({
            "situacao": situacao,
            "numero_rubrica_empresa": rubrica_empresa.codigo,
            "nome_rubrica_empresa": rubrica_empresa.nome,
            "metodo_match": metodo_match,
            "confianca_match": round(confianca_match, 2),
            "numero_rubrica_bhub": rubrica_bhub.numero if rubrica_bhub else None,
            "nome_rubrica_bhub": rubrica_bhub.nome if rubrica_bhub else None,
            "tipo_rubrica_bhub": rubrica_bhub.tipo if rubrica_bhub else tipo_rubrica_bhub,
            "natureza_rubrica": rubrica_bhub.natureza if rubrica_bhub else None,
            "conta_debito_bhub": f"{conta_debito_bhub.codigo} - {conta_debito_bhub.nome}" if conta_debito_bhub else None,
            "conta_credito_bhub": f"{conta_credito_bhub.codigo} - {conta_credito_bhub.nome}" if conta_credito_bhub else None,
            "conta_debito_empresa": _formatar_conta(conta_debito_emp),
            "conta_credito_empresa": _formatar_conta(conta_credito_emp),
            "confianca_debito": round(confianca_debito, 2),
            "confianca_credito": round(confianca_credito, 2),
            "aprovado": situacao == "ok",
        })

        if progress_callback and (i % passo_aviso == 0 or i == total):
            progress_callback(i, total)

    return pd.DataFrame(linhas)


def montar_tabela_revisao_multi(modelo, contas_empresa, rubricas_empresa, tratativas, progress_callback=None):
    """Roda montar_tabela_revisao() uma vez por tratativa (departamento) — cada
    tratativa pode ter sua própria natureza e Tipo da Integração — e devolve um
    único DataFrame combinado, com colunas extras `tratativa_id`, `departamento`
    e `tipo_integracao` pra saber de qual tratativa cada linha veio.

    `rubricas_empresa` pode ser uma lista única (mesmas rubricas pra todos os
    departamentos) ou um dict `{tratativa.id: lista de RubricaEmpresa}`, pra
    usar um conjunto diferente por departamento — usado quando a seleção vem
    por Tipo da Integração via relatorio_341 (2026-09-14: cada departamento só
    processa as rubricas do SEU tipo, ex. um departamento de Provisão só
    processa rubricas marcadas como Provisão no relatório).

    progress_callback(indice_tratativa, total_tratativas, i, total), se
    informado, é chamado periodicamente durante o processamento de cada
    tratativa."""
    tabelas = []
    total_tratativas = len(tratativas)

    for indice, tratativa in enumerate(tratativas, start=1):
        rubricas_bhub = modelo.rubricas
        if tratativa.tipo_integracao == 4:
            rubricas_bhub = bhub_model.substituir_provisao_por_rescisao(rubricas_bhub)
        modelo_ajustado = bhub_model.ModeloBhub(plano_contas=modelo.plano_contas, rubricas=rubricas_bhub)

        rubricas_desta_tratativa = (
            rubricas_empresa.get(tratativa.id, []) if isinstance(rubricas_empresa, dict) else rubricas_empresa
        )

        callback_parcial = None
        if progress_callback:
            def callback_parcial(i, total, _indice=indice, _total_tratativas=total_tratativas):
                progress_callback(_indice, _total_tratativas, i, total)

        df_tratativa = montar_tabela_revisao(
            modelo_ajustado, contas_empresa, rubricas_desta_tratativa,
            tratativa.natureza_empresa, tratativa.tipo_integracao,
            progress_callback=callback_parcial,
        )
        df_tratativa["tratativa_id"] = tratativa.id
        df_tratativa["departamento"] = tratativa.departamento
        df_tratativa["tipo_integracao"] = tratativa.tipo_integracao
        tabelas.append(df_tratativa)

    return pd.concat(tabelas, ignore_index=True) if tabelas else pd.DataFrame()


def linhas_aprovadas_para_exportacao(df):
    """Converte as linhas com aprovado=True em LinhaResolvida, prontas para
    dominio_export.gerar_arquivos_dominio() e historico_export.gerar_arquivo_historicos().

    Espera as colunas `tratativa_id`/`departamento`/`tipo_integracao` — vêm de
    montar_tabela_revisao_multi()."""
    aprovadas = df[
        (df["aprovado"])
        & df["conta_debito_empresa"].notna()
        & df["conta_credito_empresa"].notna()
    ]
    resultado = []
    for _, linha in aprovadas.iterrows():
        resultado.append(LinhaResolvida(
            descricao=linha["nome_rubrica_bhub"] or linha["nome_rubrica_empresa"],
            conta_debito_empresa=_codigo_da_conta_empresa(linha["conta_debito_empresa"]),
            conta_credito_empresa=_codigo_da_conta_empresa(linha["conta_credito_empresa"]),
            codigo_rubrica_empresa=linha["numero_rubrica_empresa"],
            tipo_rubrica_bhub=linha["tipo_rubrica_bhub"],
            natureza_rubrica=linha["natureza_rubrica"] or "-",
            numero_rubrica_bhub=linha["numero_rubrica_bhub"] or linha["numero_rubrica_empresa"],
            tratativa_id=linha["tratativa_id"],
            departamento=linha["departamento"],
            tipo_integracao=linha["tipo_integracao"],
        ))
    return resultado


def main():
    parser = argparse.ArgumentParser(description="Gera a planilha de revisão de rubricas fora do padrão BHub.")
    parser.add_argument("plano_contas_empresa")
    parser.add_argument("rubricas_empresa")
    parser.add_argument("--natureza", default="despesa_administrativa", choices=bhub_model.NATUREZAS_EMPRESA)
    parser.add_argument("--tipo-integracao", type=int, default=1, choices=sorted(bhub_model.TIPO_INTEGRACAO))
    parser.add_argument("--saida", default="revisao.xlsx")
    args = parser.parse_args()

    modelo = bhub_model.load_bhub_model(CAMINHO_PARAMETRIZACAO, CAMINHO_PLANO_CONTAS_BHUB)
    contas_empresa = empresa_loader.carregar_plano_contas_empresa(args.plano_contas_empresa)
    rubricas_empresa = empresa_loader.carregar_rubricas_empresa(args.rubricas_empresa)

    df = montar_tabela_revisao(modelo, contas_empresa, rubricas_empresa, args.natureza, args.tipo_integracao)
    df.to_excel(args.saida, index=False)
    print(f"Planilha de revisão gerada em {args.saida} ({len(df)} rubricas).")


if __name__ == "__main__":
    main()
