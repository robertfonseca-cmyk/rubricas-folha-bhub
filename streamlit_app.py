"""Interface do app de contabilização de rubricas de folha fora do padrão BHub.

Fluxo: dados fixos da empresa (código Domínio + CNPJ, não mudam no processo) ->
upload dos 2 arquivos da empresa -> ir adicionando departamentos ("+ Adicionar
departamento": natureza, Tipo da Integração, e a numeração de histórico/
lançamento DAQUELE departamento) -> tabela de revisão combinada e editável ->
geração e download de EVENTO.txt / INTEGRA.txt / Históricos.txt cobrindo todos
os departamentos adicionados, cada um com sua própria sequência de numeração.

Suporte a múltiplos departamentos no mesmo processo adicionado em 2026-08-21 a
pedido do Robert (era 1 departamento por processo até então — ver app-v1/).

Reconstruído em 2026-08-19 a partir de notas.md — ainda NÃO testado ponta a ponta
num navegador real. Ver tarefas.md.
"""

import io
import time
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

import bhub_model
import build_review
import empresa_loader
import exportar_revisao
import historico_export
from branding import (
    aplicar_tema_bhub,
    cabecalho_bhub,
    cabecalho_sidebar_bhub,
    formatar_tempo,
    secao_sidebar_bhub,
    texto_sidebar_bhub,
)
from dominio_export import gerar_arquivos_dominio
from tratativa import TratativaDepartamento

PASTA_APP = Path(__file__).parent
CAMINHO_PARAMETRIZACAO = PASTA_APP / "dados_bhub" / "[Base 141935 - Padrão 100.000] Parametrização contábil de rubricas.xlsx"
CAMINHO_PLANO_CONTAS_BHUB = PASTA_APP / "dados_bhub" / "Plano de contas padrão - PJ em Geral.xlsx"

st.set_page_config(page_title="Contabilização de Rubricas — BHub", layout="wide")
aplicar_tema_bhub()


def _exigir_senha():
    """Trava simples de acesso pra quando o app estiver hospedado (link
    acessível por qualquer um que o tenha). Só entra em vigor se existir um
    secret "app_password" configurado no ambiente de hospedagem — localmente,
    sem secrets.toml, não pede senha nenhuma. Ver README.md sobre como
    configurar isso no Streamlit Community Cloud."""
    try:
        senha_esperada = st.secrets.get("app_password")
    except Exception:
        senha_esperada = None
    if not senha_esperada:
        return
    if st.session_state.get("autenticado"):
        return

    cabecalho_bhub("Contabilização de Rubricas de Folha")
    st.markdown("#### Acesso restrito")
    senha_digitada = st.text_input("Senha de acesso", type="password", key="campo_senha")
    if senha_digitada:
        if senha_digitada == senha_esperada:
            st.session_state["autenticado"] = True
            st.rerun()
        else:
            st.error("Senha incorreta.")
    st.stop()


_exigir_senha()


@st.cache_resource
def carregar_modelo_bhub():
    return bhub_model.load_bhub_model(CAMINHO_PARAMETRIZACAO, CAMINHO_PLANO_CONTAS_BHUB)


cabecalho_sidebar_bhub()

try:
    modelo = carregar_modelo_bhub()
    modelo_ok = True
except Exception as exc:  # arquivos de referência ausentes/corrompidos
    modelo = None
    modelo_ok = False
    st.sidebar.error(f"Não consegui carregar o modelo BHub: {exc}")

# Empresa e CNPJ são fixos pro processo inteiro — não mudam entre departamentos,
# por isso vêm primeiro, antes de qualquer informação variável.
secao_sidebar_bhub("🏢", "Empresa")
codigo_empresa = st.sidebar.text_input("Código da empresa no Domínio")
cnpj_empresa = st.sidebar.text_input("CNPJ da empresa")

secao_sidebar_bhub("📁", "Arquivos")
if modelo_ok:
    texto_sidebar_bhub(
        f"Modelo BHub: {len(modelo.plano_contas)} contas, {len(modelo.rubricas)} rubricas. "
        "Envie abaixo os dois arquivos da empresa exportados do Domínio."
    )
arquivo_plano_contas = st.sidebar.file_uploader("Plano de contas da empresa (.xls/.xlsx)", type=["xls", "xlsx"])
arquivo_rubricas = st.sidebar.file_uploader("Relação de rubricas da empresa (.xls/.xlsx)", type=["xls", "xlsx"])

cabecalho_bhub("Contabilização de Rubricas de Folha")

if "departamentos" not in st.session_state:
    st.session_state.departamentos = []
if "proximo_id_departamento" not in st.session_state:
    st.session_state.proximo_id_departamento = 1
if "tabela_revisao" not in st.session_state:
    st.session_state.tabela_revisao = None

if not modelo_ok:
    st.stop()

# --- 1. Departamentos a processar -------------------------------------------
st.markdown("### 1. Departamentos a processar")
st.caption(
    "Um mesmo processo pode cobrir mais de um departamento — cada um pode ter "
    "natureza diferente (ou não) e sua própria sequência de histórico/lançamento. "
    "Adicione um por vez com o botão abaixo."
)

with st.form("form_novo_departamento", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1:
        natureza_empresa_novo = st.selectbox(
            "Natureza (coluna do modelo BHub a usar)",
            options=bhub_model.NATUREZAS_EMPRESA,
            format_func=lambda v: bhub_model.NATUREZAS_EMPRESA_LABELS[v],
        )
        departamento_novo = st.text_input("Departamento (código gravado no EVENTO/INTEGRA)")
    with col2:
        tipo_integracao_novo = st.selectbox(
            "Tipo da Integração",
            options=sorted(bhub_model.TIPO_INTEGRACAO_LABELS),
            format_func=lambda v: bhub_model.TIPO_INTEGRACAO_LABELS[v],
        )
        ultimo_historico_novo = st.number_input("Último histórico já cadastrado (deste departamento)", min_value=0, step=1)
        ultimo_lancamento_novo = st.number_input("Último lançamento já cadastrado (deste departamento)", min_value=0, step=1)

    if tipo_integracao_novo == 3:
        st.warning(
            "Tipo 3 (Férias) só é habilitado em casos específicos no Domínio — na "
            "maioria dos casos, use o tipo 1 (Folha mensal), que já contabiliza as "
            "rubricas de férias no modelo BHub."
        )

    adicionar = st.form_submit_button("➕ Adicionar departamento")
    if adicionar:
        if not departamento_novo:
            st.warning("Informe o código do departamento antes de adicionar.")
        else:
            st.session_state.departamentos.append(TratativaDepartamento(
                id=st.session_state.proximo_id_departamento,
                departamento=departamento_novo,
                natureza_empresa=natureza_empresa_novo,
                tipo_integracao=tipo_integracao_novo,
                ultimo_historico=int(ultimo_historico_novo),
                ultimo_lancamento=int(ultimo_lancamento_novo),
            ))
            st.session_state.proximo_id_departamento += 1

if st.session_state.departamentos:
    st.caption("Pode editar qualquer campo de um departamento já adicionado direto na tabela abaixo.")
    df_departamentos = pd.DataFrame([
        {
            "id": t.id,
            "departamento": t.departamento,
            "natureza": t.natureza_empresa,
            "tipo_integracao": t.tipo_integracao,
            "ultimo_historico": t.ultimo_historico,
            "ultimo_lancamento": t.ultimo_lancamento,
            "remover": False,
        }
        for t in st.session_state.departamentos
    ])
    df_departamentos_editado = st.data_editor(
        df_departamentos,
        width="stretch",
        hide_index=True,
        disabled=["id"],
        column_config={
            "departamento": st.column_config.TextColumn("Departamento"),
            "natureza": st.column_config.SelectboxColumn(
                "Natureza",
                options=bhub_model.NATUREZAS_EMPRESA,
                format_func=lambda v: bhub_model.NATUREZAS_EMPRESA_LABELS[v],
            ),
            "tipo_integracao": st.column_config.SelectboxColumn(
                "Tipo da Integração",
                options=sorted(bhub_model.TIPO_INTEGRACAO_LABELS),
                format_func=lambda v: bhub_model.TIPO_INTEGRACAO_LABELS[v],
            ),
            "ultimo_historico": st.column_config.NumberColumn("Último histórico", min_value=0, step=1),
            "ultimo_lancamento": st.column_config.NumberColumn("Último lançamento", min_value=0, step=1),
            "remover": st.column_config.CheckboxColumn("Remover"),
        },
        key="editor_departamentos",
    )

    # Aplica edições e remoções de volta na lista de departamentos. Comparar
    # com a lista atual antes de reatribuir evita um rerun em loop quando nada
    # mudou de fato.
    departamentos_editados = [
        TratativaDepartamento(
            id=int(linha["id"]),
            departamento=linha["departamento"],
            natureza_empresa=linha["natureza"],
            tipo_integracao=int(linha["tipo_integracao"]),
            ultimo_historico=int(linha["ultimo_historico"]),
            ultimo_lancamento=int(linha["ultimo_lancamento"]),
        )
        for _, linha in df_departamentos_editado.iterrows()
        if not linha["remover"]
    ]
    if departamentos_editados != st.session_state.departamentos:
        st.session_state.departamentos = departamentos_editados
        st.rerun()
else:
    st.info("Nenhum departamento adicionado ainda.")

# --- 2. Gerar tabela de revisão ----------------------------------------------
st.markdown("### 2. Gerar tabela de revisão")
pode_processar = (
    arquivo_plano_contas is not None
    and arquivo_rubricas is not None
    and len(st.session_state.departamentos) > 0
)
if not pode_processar:
    st.info("Envie os dois arquivos da empresa e adicione ao menos um departamento para liberar o processamento.")

if st.button("Processar rubricas da empresa", disabled=not pode_processar):
    contas_empresa = empresa_loader.carregar_plano_contas_empresa(arquivo_plano_contas)
    rubricas_empresa = empresa_loader.carregar_rubricas_empresa(arquivo_rubricas)

    total_departamentos = len(st.session_state.departamentos)
    barra = st.progress(0.0)
    status = st.empty()
    inicio = time.monotonic()

    def _atualizar_progresso(indice_departamento, total_deptos, i, total):
        decorrido = time.monotonic() - inicio
        feito = (indice_departamento - 1) / total_deptos + (i / total) / total_deptos if total else 0
        restante = (decorrido / feito - decorrido) if feito else 0
        barra.progress(min(feito, 1.0))
        status.text(
            f"Departamento {indice_departamento}/{total_deptos} — {i}/{total} rubricas "
            f"— tempo restante estimado: {formatar_tempo(restante)}"
        )

    st.session_state.tabela_revisao = build_review.montar_tabela_revisao_multi(
        modelo, contas_empresa, rubricas_empresa, st.session_state.departamentos,
        progress_callback=_atualizar_progresso,
    )
    barra.empty()
    status.empty()

df = st.session_state.tabela_revisao

if df is not None and not df.empty:
    st.markdown("### 3. Revisão")

    st.markdown("#### Por departamento")
    resumo = (
        df.groupby(["departamento", "situacao"]).size().unstack(fill_value=0)
    )
    st.dataframe(resumo, width="stretch")

    departamentos_disponiveis = sorted(df["departamento"].unique())
    departamentos_selecionados = st.multiselect(
        "Departamento(s) para revisar (deixe todos marcados para revisar de uma vez só)",
        options=departamentos_disponiveis,
        default=departamentos_disponiveis,
    )

    df_filtrado = df[df["departamento"].isin(departamentos_selecionados)]
    contagem = df_filtrado["situacao"].value_counts()
    col1, col2, col3 = st.columns(3)
    col1.metric("Aprovadas", int((df_filtrado["situacao"] == "ok").sum()))
    col2.metric("Informativas sem contabilização", int(contagem.get("informativa_sem_contabilizacao", 0)))
    col3.metric("Precisam de revisão", int(len(df_filtrado) - (df_filtrado["situacao"] == "ok").sum() - contagem.get("informativa_sem_contabilizacao", 0)))

    df_visivel = df_filtrado[df_filtrado["situacao"] != "informativa_sem_contabilizacao"].copy()
    df_editado = st.data_editor(
        df_visivel,
        width="stretch",
        num_rows="fixed",
        column_config={"aprovado": st.column_config.CheckboxColumn("Aprovado")},
        key="editor_revisao",
    )
    # Grava as edições de volta na tabela mestra (por índice, todas as colunas
    # editadas — não só "aprovado") — assim, trocar o filtro de departamento não
    # perde a revisão já feita nos outros.
    st.session_state.tabela_revisao.loc[df_editado.index, df_editado.columns] = df_editado
    df = st.session_state.tabela_revisao

    # A tabela completa pra exportação sempre cobre TODOS os departamentos já
    # revisados (o filtro acima é só pra facilitar a tela, não restringe o que
    # vai pro arquivo final).
    df_completo = df

    st.markdown("#### Baixar tabela de revisão")
    formato = st.selectbox("Formato", options=list(exportar_revisao.FORMATOS))
    info_formato = exportar_revisao.FORMATOS[formato]
    conteudo = info_formato["gerador"](df_completo)
    st.download_button(
        f"Baixar revisão ({formato})",
        data=conteudo,
        file_name=f"revisao_rubricas.{info_formato['extensao']}",
        mime=info_formato["mime"],
    )

    st.markdown("#### Reenviar tabela de revisão corrigida")
    st.caption(
        "Baixou a tabela acima, corrigiu no Excel (contas, aprovação, o que for) "
        "e quer aplicar de volta em vez de editar linha a linha na tela? Envie o "
        "arquivo aqui (CSV ou XLSX — não o PDF, que só tem um recorte de colunas)."
    )
    arquivo_revisao_corrigida = st.file_uploader(
        "Tabela de revisão corrigida", type=["csv", "xlsx"], key="upload_revisao_corrigida"
    )
    if arquivo_revisao_corrigida is not None:
        if st.button("Aplicar correções do arquivo enviado"):
            if arquivo_revisao_corrigida.name.lower().endswith(".csv"):
                df_corrigido = pd.read_csv(arquivo_revisao_corrigida)
            else:
                df_corrigido = pd.read_excel(arquivo_revisao_corrigida)

            colunas_chave = ["tratativa_id", "numero_rubrica_empresa"]
            faltando = [c for c in colunas_chave if c not in df_corrigido.columns]
            if faltando:
                st.error(
                    f"O arquivo enviado não tem as colunas {', '.join(faltando)}, "
                    "necessárias pra saber qual linha é qual — baixe a tabela desta "
                    "tela, edite por cima dela, e envie de volta sem remover colunas."
                )
            else:
                # dtype "object" nas duas pontas: o pandas 3.0 usa por padrão
                # um dtype de texto estrito (Arrow) que rejeita gravar um
                # inteiro ou um NaN puro numa coluna que ele decidiu que é
                # "str" — bateu nisso tanto com `.loc[...] = ...` quanto com
                # `DataFrame.update()`. "object" aceita qualquer valor Python
                # livremente, igual o pandas se comportava antes da v3.
                mestre = st.session_state.tabela_revisao.copy().astype(object)
                df_corrigido = df_corrigido.astype(object)

                chave_mestre = mestre["tratativa_id"].astype(str) + "|" + mestre["numero_rubrica_empresa"].astype(str)
                chave_corrigido = df_corrigido["tratativa_id"].astype(str) + "|" + df_corrigido["numero_rubrica_empresa"].astype(str)

                mestre.index = chave_mestre
                df_corrigido.index = chave_corrigido
                # As colunas-chave identificam a linha — não "corrigir" (e o
                # CSV muda o tipo delas: vira int, perde zero à esquerda etc.
                # se o pandas inferir número — só usar pra achar a linha certa).
                colunas_para_atualizar = [
                    c for c in df_corrigido.columns if c in mestre.columns and c not in colunas_chave
                ]

                chaves_validas = df_corrigido.index[df_corrigido.index.isin(mestre.index)]
                chaves_invalidas = len(df_corrigido) - len(chaves_validas)

                # Atualização célula a célula, pulando NaN — célula vazia na
                # planilha não apaga o valor original.
                for chave in chaves_validas:
                    linha_corrigida = df_corrigido.loc[chave]
                    for coluna in colunas_para_atualizar:
                        valor = linha_corrigida[coluna]
                        if pd.notna(valor):
                            mestre.at[chave, coluna] = valor

                mestre["aprovado"] = mestre["aprovado"].astype(bool)
                st.session_state.tabela_revisao = mestre.reset_index(drop=True)

                st.success(f"{len(chaves_validas)} linha(s) atualizadas a partir do arquivo enviado.")
                if chaves_invalidas:
                    st.warning(
                        f"{chaves_invalidas} linha(s) do arquivo enviado não bateram com "
                        "nenhuma linha da tabela atual (a tabela pode ter sido reprocessada "
                        "depois que você baixou esse arquivo) — foram ignoradas."
                    )
                st.rerun()

    st.markdown("### 4. Gerar arquivos para o Domínio")
    campos_obrigatorios_ok = bool(codigo_empresa) and bool(cnpj_empresa)
    if not campos_obrigatorios_ok:
        st.info("Preencha código da empresa e CNPJ na barra lateral para liberar a geração dos arquivos.")

    departamentos_para_exportar = sorted(df_completo["departamento"].unique())
    tipos_para_exportar = sorted(df_completo["tipo_integracao"].unique())

    col_filtro_dep, col_filtro_tipo = st.columns(2)
    with col_filtro_dep:
        departamentos_selecionados_export = st.multiselect(
            "Departamento(s) a exportar",
            options=departamentos_para_exportar,
            default=departamentos_para_exportar,
            key="export_departamentos",
        )
    with col_filtro_tipo:
        tipos_selecionados_export = st.multiselect(
            "Tipo(s) de Integração a exportar",
            options=tipos_para_exportar,
            default=tipos_para_exportar,
            format_func=lambda v: bhub_model.TIPO_INTEGRACAO_LABELS.get(v, str(v)),
            key="export_tipos_integracao",
        )

    modo_exportacao = st.radio(
        "Como emitir",
        options=["combinado", "separado"],
        format_func=lambda v: (
            "Um arquivo combinado (todos os departamentos/tipos selecionados juntos)"
            if v == "combinado"
            else "Um arquivo por departamento (separados, dentro de um .zip)"
        ),
        horizontal=True,
    )

    if st.button("Gerar EVENTO / INTEGRA / Históricos", disabled=not campos_obrigatorios_ok):
        linhas_resolvidas = build_review.linhas_aprovadas_para_exportacao(df_completo)
        linhas_filtradas = [
            linha for linha in linhas_resolvidas
            if linha.departamento in departamentos_selecionados_export
            and linha.tipo_integracao in tipos_selecionados_export
        ]
        if not linhas_filtradas:
            st.warning("Nenhuma linha aprovada dentro do filtro escolhido — nada para gerar.")
        else:
            numeracao_por_tratativa = {
                t.id: {"ultimo_historico": t.ultimo_historico, "ultimo_lancamento": t.ultimo_lancamento}
                for t in st.session_state.departamentos
            }

            if modo_exportacao == "combinado":
                evento_txt, integra_txt, linhas_numeradas = gerar_arquivos_dominio(
                    linhas_filtradas, codigo_empresa, numeracao_por_tratativa,
                )
                historicos_txt, avisos = historico_export.gerar_arquivo_historicos(linhas_numeradas, cnpj_empresa)

                if avisos:
                    st.warning(
                        f"{len(avisos)} histórico(s) usaram um template ainda não confirmado "
                        "com o Robert para este tipo/natureza de rubrica — revise antes de "
                        "importar no Domínio."
                    )

                departamentos_gerados = sorted({linha.departamento for linha in linhas_filtradas})
                st.success(
                    f"{len(linhas_filtradas)} rubricas geradas, cobrindo {len(departamentos_gerados)} "
                    f"departamento(s): {', '.join(departamentos_gerados)}."
                )
                c1, c2, c3 = st.columns(3)
                c1.download_button("Baixar EVENTO.txt", data=evento_txt, file_name="EVENTO.txt", mime="text/plain")
                c2.download_button("Baixar INTEGRA.txt", data=integra_txt, file_name="INTEGRA.txt", mime="text/plain")
                c3.download_button("Baixar Históricos.txt", data=historicos_txt, file_name="Historicos.txt", mime="text/plain")
            else:
                buffer_zip = io.BytesIO()
                avisos_totais = 0
                with zipfile.ZipFile(buffer_zip, "w", zipfile.ZIP_DEFLATED) as arquivo_zip:
                    for departamento in departamentos_selecionados_export:
                        linhas_departamento = [l for l in linhas_filtradas if l.departamento == departamento]
                        if not linhas_departamento:
                            continue
                        evento_txt, integra_txt, linhas_numeradas = gerar_arquivos_dominio(
                            linhas_departamento, codigo_empresa, numeracao_por_tratativa,
                        )
                        historicos_txt, avisos = historico_export.gerar_arquivo_historicos(linhas_numeradas, cnpj_empresa)
                        avisos_totais += len(avisos)
                        sufixo = "".join(c if c.isalnum() else "_" for c in departamento)
                        arquivo_zip.writestr(f"EVENTO_{sufixo}.txt", evento_txt)
                        arquivo_zip.writestr(f"INTEGRA_{sufixo}.txt", integra_txt)
                        arquivo_zip.writestr(f"Historicos_{sufixo}.txt", historicos_txt)

                if avisos_totais:
                    st.warning(
                        f"{avisos_totais} histórico(s), no total, usaram um template ainda não "
                        "confirmado com o Robert para aquele tipo/natureza de rubrica — revise "
                        "antes de importar no Domínio."
                    )

                st.success(
                    f"{len(linhas_filtradas)} rubricas geradas, em "
                    f"{len(departamentos_selecionados_export)} arquivo(s) separado(s) por departamento."
                )
                st.download_button(
                    "Baixar arquivos separados por departamento (.zip)",
                    data=buffer_zip.getvalue(),
                    file_name="rubricas_por_departamento.zip",
                    mime="application/zip",
                )
