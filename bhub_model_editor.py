"""Tela pra consultar e alterar o padrão de contabilização BHub (rubricas +
plano de contas) direto pelo app — sem precisar editar os .xlsx de
dados_bhub/ na mão.

Adicionado em 2026-09-24 a pedido do Robert: "preciso de uma forma que quando
precisarmos consultar o padrão de contabilização da BHub seja possível, tanto
consultar quando alterar". Decisões confirmadas com ele:
- Cobre RUBRICAS (débito/crédito por natureza da empresa) E plano de contas
  BHub, não só um dos dois.
- Salvar aqui SOBRESCREVE direto os .xlsx de dados_bhub/ (sem versionamento/
  backup) — o próximo processamento de qualquer pessoa no app já usa a
  versão nova.

IMPORTANTE — por que a escrita é célula a célula, e não recriar o arquivo do
zero: inspecionando os .xlsx reais, cada um tem MUITO mais dado do que este
app lê. A parametrização de rubricas tem 8 abas (só 5 são lidas aqui: Folha/
Rescisão/Empresa/Provisão de Férias/Provisão de 13º) — "Plano de Contas Bhub"
e "Conferencia" são abas à parte, não tocadas. Cada aba de rubrica lida tem
colunas extras não usadas (ex. "Histórico"/"Lançamento" na Folha). O plano de
contas tem colunas extras (Mascara_conta, Código_RFB, Descrição_RFB, etc.) e
3 abas extras (Cópia, L100A, L300A). Reescrever do zero apagaria tudo isso.
Por isso: abre o .xlsx original, localiza as linhas/colunas certas pelas
MESMAS regras de bhub_model.py, e só sobrescreve as células que este app
realmente usa — o resto do arquivo (outras abas, outras colunas, formatação)
fica intacto.
"""

import openpyxl
import pandas as pd
import streamlit as st

import bhub_model

_COLUNAS_CONTAS_POR_NATUREZA = [
    f"{natureza}_{sufixo}"
    for natureza in bhub_model.NATUREZAS_EMPRESA
    for sufixo in ("debito", "credito")
]


def _texto(valor):
    if valor is None or (isinstance(valor, float) and pd.isna(valor)) or (isinstance(valor, str) and not valor.strip()):
        return ""
    if pd.isna(valor):
        return ""
    texto = str(valor).strip()
    return texto[:-2] if texto.endswith(".0") else texto


# ---------------------------------------------------------------------------
# Rubricas — DataFrame <-> RubricaBhub, pra exibir/editar no data_editor
# ---------------------------------------------------------------------------

def rubricas_para_dataframe(rubricas, incluir_esocial):
    linhas = []
    for r in rubricas:
        linha = {"numero": r.numero, "nome": r.nome, "natureza": r.natureza}
        if incluir_esocial:
            linha["codigo_esocial"] = r.codigo_esocial
        for natureza_empresa in bhub_model.NATUREZAS_EMPRESA:
            deb, cred = r.contas.get(natureza_empresa, ("", ""))
            linha[f"{natureza_empresa}_debito"] = deb
            linha[f"{natureza_empresa}_credito"] = cred
        linhas.append(linha)
    colunas = ["numero", "nome", "natureza"] + (["codigo_esocial"] if incluir_esocial else []) + _COLUNAS_CONTAS_POR_NATUREZA
    return pd.DataFrame(linhas, columns=colunas)


def dataframe_para_rubricas(df, tipo, incluir_esocial):
    rubricas = []
    for _, linha in df.iterrows():
        numero = _texto(linha.get("numero"))
        if not numero:
            continue
        contas = {}
        for natureza_empresa in bhub_model.NATUREZAS_EMPRESA:
            deb = _texto(linha.get(f"{natureza_empresa}_debito"))
            cred = _texto(linha.get(f"{natureza_empresa}_credito"))
            if deb and cred:
                contas[natureza_empresa] = (deb, cred)
        rubricas.append(bhub_model.RubricaBhub(
            numero=numero,
            nome=_texto(linha.get("nome")),
            natureza=_texto(linha.get("natureza")) or "-",
            tipo=tipo,
            contas=contas,
            codigo_esocial=_texto(linha.get("codigo_esocial")) if incluir_esocial else "",
        ))
    return rubricas


# ---------------------------------------------------------------------------
# Plano de contas — DataFrame <-> ContaBhub
# ---------------------------------------------------------------------------

def plano_contas_para_dataframe(plano_contas):
    linhas = [
        {"codigo": c.codigo, "nome": c.nome, "grupo_da_conta": c.grupo_da_conta, "natureza (calculada)": c.natureza}
        for c in sorted(plano_contas.values(), key=lambda c: c.codigo)
    ]
    return pd.DataFrame(linhas, columns=["codigo", "nome", "grupo_da_conta", "natureza (calculada)"])


def dataframe_para_plano_contas(df):
    plano = {}
    for _, linha in df.iterrows():
        codigo = _texto(linha.get("codigo"))
        if not codigo:
            continue
        grupo = _texto(linha.get("grupo_da_conta"))
        plano[codigo] = bhub_model.ContaBhub(
            codigo=codigo,
            nome=_texto(linha.get("nome")),
            grupo_da_conta=grupo,
            natureza=bhub_model.derivar_natureza_por_nome(grupo),
        )
    return plano


# ---------------------------------------------------------------------------
# Escrita célula a célula (preserva tudo que o app não usa)
# ---------------------------------------------------------------------------

def _linha_esta_vazia(ws, linha, colunas):
    return all(ws.cell(row=linha, column=c).value in (None, "") for c in colunas)


def salvar_rubricas_de_um_tipo(caminho_parametrizacao, tipo, rubricas_novas):
    """Sobrescreve SÓ a aba de `tipo` (ex. 'Folha') com `rubricas_novas`
    (list[RubricaBhub]) e, se `tipo == 'folha'`, também a aba de
    correspondência eSocial (só as linhas de codi_emp == CODI_EMP_BASE, que é
    o recorte que bhub_model já lê de volta) — célula a célula, sem tocar em
    nenhuma outra aba/coluna do arquivo."""
    wb = openpyxl.load_workbook(caminho_parametrizacao, data_only=True)
    nome_aba = bhub_model.SHEETS_RUBRICAS[tipo]
    ws = bhub_model._obter_aba(wb, nome_aba)
    linha_cab = bhub_model._localizar_linha_cabecalho(ws)
    col_numero, col_nome, col_natureza, pares_natureza = bhub_model.mapear_colunas_rubricas(ws, linha_cab)
    colunas_geridas = [col_numero, col_nome] + ([col_natureza] if col_natureza else [])
    for par in pares_natureza:
        colunas_geridas += [par["debito"], par["credito"]]

    # Mapeia número -> linha das rubricas JÁ existentes na aba, pra saber quem
    # atualizar in-place e quem sobrou (a apagar).
    linha_por_numero = {}
    ultima_linha_com_dado = linha_cab
    for linha in range(linha_cab + 1, ws.max_row + 1):
        numero = _texto(ws.cell(row=linha, column=col_numero).value)
        if numero:
            linha_por_numero[numero] = linha
            ultima_linha_com_dado = linha

    numeros_novos = {r.numero for r in rubricas_novas}
    duplicados = [n for n in numeros_novos if list(r.numero for r in rubricas_novas).count(n) > 1]
    if duplicados:
        raise ValueError(f"Número(s) de rubrica repetido(s) na tabela: {', '.join(sorted(set(duplicados)))}.")

    proxima_linha_livre = ultima_linha_com_dado + 1
    for r in rubricas_novas:
        linha = linha_por_numero.get(r.numero)
        if linha is None:
            linha = proxima_linha_livre
            proxima_linha_livre += 1
        ws.cell(row=linha, column=col_numero, value=_valor_numero(r.numero))
        ws.cell(row=linha, column=col_nome, value=r.nome)
        if col_natureza:
            ws.cell(row=linha, column=col_natureza, value=r.natureza)
        for par, natureza_empresa in zip(pares_natureza, bhub_model.NATUREZAS_EMPRESA):
            deb, cred = r.contas.get(natureza_empresa, ("", ""))
            ws.cell(row=linha, column=par["debito"], value=_valor_numero(deb) if deb else None)
            ws.cell(row=linha, column=par["credito"], value=_valor_numero(cred) if cred else None)

    linhas_a_remover = sorted(
        (linha for numero, linha in linha_por_numero.items() if numero not in numeros_novos),
        reverse=True,
    )
    for linha in linhas_a_remover:
        ws.delete_rows(linha, 1)

    if tipo == "folha":
        _salvar_esocial(wb, rubricas_novas)

    wb.save(caminho_parametrizacao)


def _valor_numero(texto):
    """Mantém como texto puro — os arquivos originais guardam Nº/contas às
    vezes como número (1.0) às vezes como texto; texto puro é inequívoco e é
    exatamente o que bhub_model._limpar_codigo sabe ler de volta dos dois
    jeitos."""
    return texto


def _salvar_esocial(wb, rubricas_folha):
    """Reescreve só as linhas de codi_emp == CODI_EMP_BASE na aba de
    correspondência eSocial — é o único recorte que
    bhub_model._carregar_esocial_por_numero lê de volta; outras linhas
    (outras empresas-base) e outras colunas dessa aba ficam intactas."""
    ws = bhub_model._obter_aba(wb, bhub_model.ABA_RELACAO_ESOCIAL)
    idx = bhub_model._indice_colunas(ws, 1)
    col_i_eventos = idx.get("i_eventos")
    col_codi_emp = idx.get("codi_emp")
    col_esocial = idx.get("codigo_esocial")
    if not (col_i_eventos and col_codi_emp and col_esocial):
        return  # aba sem essas colunas — não dá pra gravar eSocial, mas não quebra o resto

    linha_por_numero = {}
    ultima_linha_com_dado = 1
    for linha in range(2, ws.max_row + 1):
        codi_emp = _texto(ws.cell(row=linha, column=col_codi_emp).value)
        if codi_emp != bhub_model.CODI_EMP_BASE:
            if ws.cell(row=linha, column=col_i_eventos).value not in (None, ""):
                ultima_linha_com_dado = max(ultima_linha_com_dado, linha)
            continue
        numero = _texto(ws.cell(row=linha, column=col_i_eventos).value)
        if numero:
            linha_por_numero[numero] = linha
        ultima_linha_com_dado = max(ultima_linha_com_dado, linha)

    numeros_com_esocial = {r.numero: r.codigo_esocial for r in rubricas_folha if r.codigo_esocial}

    proxima_linha_livre = ultima_linha_com_dado + 1
    for numero, codigo_esocial in numeros_com_esocial.items():
        linha = linha_por_numero.get(numero)
        if linha is None:
            linha = proxima_linha_livre
            proxima_linha_livre += 1
            ws.cell(row=linha, column=col_i_eventos, value=numero)
            ws.cell(row=linha, column=col_codi_emp, value=bhub_model.CODI_EMP_BASE)
        ws.cell(row=linha, column=col_esocial, value=codigo_esocial)

    linhas_a_remover = sorted(
        (linha for numero, linha in linha_por_numero.items() if numero not in numeros_com_esocial),
        reverse=True,
    )
    for linha in linhas_a_remover:
        ws.delete_rows(linha, 1)


def salvar_plano_contas(caminho_plano_contas, plano_contas_novo):
    """Sobrescreve só as contas ANALÍTICAS (tipo_conta == 'A') — o único
    recorte que bhub_model.carregar_plano_contas lê — célula a célula, sem
    tocar nas contas sintéticas nem nas outras colunas/abas do arquivo."""
    wb = openpyxl.load_workbook(caminho_plano_contas, data_only=True)
    ws = bhub_model._obter_aba(wb, bhub_model.ABA_PLANO_CONTAS)
    idx = bhub_model._indice_colunas(ws, 1)
    col_codigo = idx["codigo_conta"]
    col_nome = idx["nome_conta"]
    col_tipo = idx["tipo_conta"]
    col_grupo = idx["grupo da conta"]

    linha_por_codigo = {}
    ultima_linha_com_dado = 1
    for linha in range(2, ws.max_row + 1):
        tipo_conta = str(ws.cell(row=linha, column=col_tipo).value or "").strip().upper()
        codigo_bruto = ws.cell(row=linha, column=col_codigo).value
        if codigo_bruto not in (None, ""):
            ultima_linha_com_dado = max(ultima_linha_com_dado, linha)
        if tipo_conta != "A":
            continue
        codigo = _texto(codigo_bruto)
        if codigo:
            linha_por_codigo[codigo] = linha

    codigos_novos = {c.codigo for c in plano_contas_novo.values()}
    proxima_linha_livre = ultima_linha_com_dado + 1
    for conta in plano_contas_novo.values():
        linha = linha_por_codigo.get(conta.codigo)
        if linha is None:
            linha = proxima_linha_livre
            proxima_linha_livre += 1
            ws.cell(row=linha, column=col_codigo, value=conta.codigo)
            ws.cell(row=linha, column=col_tipo, value="A")
        ws.cell(row=linha, column=col_nome, value=conta.nome)
        ws.cell(row=linha, column=col_grupo, value=conta.grupo_da_conta)

    linhas_a_remover = sorted(
        (linha for codigo, linha in linha_por_codigo.items() if codigo not in codigos_novos),
        reverse=True,
    )
    for linha in linhas_a_remover:
        ws.delete_rows(linha, 1)

    wb.save(caminho_plano_contas)


# ---------------------------------------------------------------------------
# Busca — filtra só o que é MOSTRADO na tela; salvar sempre mescla de volta
# no conjunto completo (ver _mesclar_edicao_parcial), então buscar e editar só
# a linha encontrada nunca apaga as que ficaram de fora do resultado.
# ---------------------------------------------------------------------------

def _filtrar_por_texto(df, busca, colunas):
    if not busca:
        return df
    busca_norm = busca.strip().lower()
    mascara = False
    for coluna in colunas:
        mascara = mascara | df[coluna].astype(str).str.lower().str.contains(busca_norm, regex=False)
    return df[mascara]


def _mesclar_edicao_parcial(itens_completos_por_chave, chaves_mostradas_antes_da_edicao, itens_editados):
    """`itens_completos_por_chave`: TODOS os itens (dict chave -> objeto), do
    jeito que estavam antes desta edição. `chaves_mostradas_antes_da_edicao`:
    as chaves que estavam visíveis na tabela (com busca ativa, só as que
    bateram no filtro) ANTES do usuário editar. `itens_editados`: o resultado
    de converter de volta a tabela editada (só a parte que estava visível).

    Devolve a lista completa resultante: item fora do filtro = preservado
    como estava; item que estava visível e sumiu da edição = removido; item
    editado/novo = entra com o valor novo. Isso é o que permite buscar,
    editar só o que apareceu, e salvar sem arriscar apagar o resto."""
    resultado = dict(itens_completos_por_chave)
    for chave in chaves_mostradas_antes_da_edicao:
        resultado.pop(chave, None)
    for item in itens_editados:
        resultado[item.numero if hasattr(item, "numero") else item.codigo] = item
    return list(resultado.values())


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def pagina_padrao_bhub(modelo, modelo_ok, caminho_parametrizacao, caminho_plano_contas, limpar_cache_modelo):
    st.markdown("### Padrão de contabilização BHub")
    st.caption(
        "Consulte e altere aqui o modelo de referência usado no matching — as rubricas "
        "padrão (débito/crédito por natureza da empresa) e o plano de contas padrão BHub. "
        "**Salvar aqui sobrescreve os arquivos usados por todo mundo que abrir o app** (sem "
        "backup automático) — a mudança já vale a partir do próximo processamento de "
        "qualquer pessoa. Use a busca no topo de cada tabela pra achar a rubrica/conta antes "
        "de editar."
    )

    if not modelo_ok:
        st.error("O modelo BHub não carregou — não dá pra consultar nem alterar agora.")
        return

    tipos = list(bhub_model.SHEETS_RUBRICAS)
    nomes_abas = [bhub_model.SHEETS_RUBRICAS[t] for t in tipos] + ["Plano de contas"]
    abas = st.tabs(nomes_abas)

    for tipo, aba in zip(tipos, abas[:-1]):
        with aba:
            incluir_esocial = tipo == "folha"
            rubricas_do_tipo = modelo.rubricas_por_tipo(tipo)
            df_rubricas = rubricas_para_dataframe(rubricas_do_tipo, incluir_esocial)

            busca = st.text_input(
                "🔍 Buscar rubrica (número ou nome)",
                key=f"busca_padrao_bhub_{tipo}",
                placeholder="ex.: 336 ou SALARIO",
            )
            df_mostrado = _filtrar_por_texto(df_rubricas, busca, ["numero", "nome"])
            if busca:
                st.caption(
                    f"{len(df_mostrado)} de {len(df_rubricas)} rubrica(s) encontrada(s). Editar e "
                    "trocar o texto da busca ANTES de clicar em salvar descarta a edição ainda não "
                    "salva desta aba (nada se perde no arquivo — só o que ainda não foi salvo na tela)."
                )
            else:
                st.caption(
                    f"{len(df_rubricas)} rubrica(s). Deixe Débito e Crédito em branco numa natureza "
                    "pra essa natureza não gerar lançamento pra essa rubrica. Use os controles da "
                    "tabela pra adicionar/remover linhas."
                )
            df_editado = st.data_editor(
                df_mostrado,
                width="stretch",
                num_rows="dynamic",
                height=420,
                key=f"editor_padrao_bhub_rubricas_{tipo}_{busca}",
                column_config={
                    "natureza": st.column_config.SelectboxColumn(options=["P", "D", "I", "ID", "-"]),
                },
            )
            if st.button(f"Salvar \"{bhub_model.SHEETS_RUBRICAS[tipo]}\"", key=f"salvar_padrao_bhub_{tipo}"):
                try:
                    subset_editado = dataframe_para_rubricas(df_editado, tipo, incluir_esocial)
                    rubricas_completas_por_numero = {r.numero: r for r in rubricas_do_tipo}
                    chaves_mostradas = set(df_mostrado["numero"])
                    rubricas_novas = _mesclar_edicao_parcial(
                        rubricas_completas_por_numero, chaves_mostradas, subset_editado
                    )
                    salvar_rubricas_de_um_tipo(caminho_parametrizacao, tipo, rubricas_novas)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    limpar_cache_modelo()
                    st.success(f"\"{bhub_model.SHEETS_RUBRICAS[tipo]}\" salva — recarregando o modelo atualizado...")
                    st.rerun()

    with abas[-1]:
        df_contas = plano_contas_para_dataframe(modelo.plano_contas)

        busca_contas = st.text_input(
            "🔍 Buscar conta (código ou nome)",
            key="busca_padrao_bhub_plano_contas",
            placeholder="ex.: 2001 ou CAIXA",
        )
        df_contas_mostrado = _filtrar_por_texto(df_contas, busca_contas, ["codigo", "nome"])
        if busca_contas:
            st.caption(
                f"{len(df_contas_mostrado)} de {len(df_contas)} conta(s) encontrada(s). Editar e "
                "trocar o texto da busca ANTES de clicar em salvar descarta a edição ainda não "
                "salva desta aba (nada se perde no arquivo — só o que ainda não foi salvo na tela)."
            )
        else:
            st.caption(
                f"{len(df_contas)} conta(s) analítica(s) (só essas entram no matching — contas "
                "sintéticas do plano original não aparecem aqui nem são afetadas ao salvar). "
                "\"natureza (calculada)\" é só informativo: vem do texto em \"grupo_da_conta\" "
                "— contas do MESMO grupo têm que usar o MESMO texto pra caírem na mesma natureza."
            )
        df_contas_editado = st.data_editor(
            df_contas_mostrado,
            width="stretch",
            num_rows="dynamic",
            height=420,
            key=f"editor_padrao_bhub_plano_contas_{busca_contas}",
            column_config={"natureza (calculada)": st.column_config.TextColumn(disabled=True)},
        )
        if st.button("Salvar plano de contas", key="salvar_padrao_bhub_plano_contas"):
            subset_editado_dict = dataframe_para_plano_contas(df_contas_editado)
            chaves_mostradas = set(df_contas_mostrado["codigo"])
            plano_contas_novo_lista = _mesclar_edicao_parcial(
                dict(modelo.plano_contas), chaves_mostradas, list(subset_editado_dict.values())
            )
            plano_contas_novo = {c.codigo: c for c in plano_contas_novo_lista}
            salvar_plano_contas(caminho_plano_contas, plano_contas_novo)
            limpar_cache_modelo()
            st.success("Plano de contas salvo — recarregando o modelo atualizado...")
            st.rerun()
