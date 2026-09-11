"""Equivalência de rubrica (empresa -> BHub) e de conta (BHub -> plano da empresa).

Reconstruído em 2026-08-19 a partir de notas.md.
"""

import re
from difflib import SequenceMatcher

# Siglas de tributo — usadas para não deixar a similaridade de texto confundir
# tributos diferentes com nomes parecidos (achado real: "INSS A RECUPERAR" batendo
# com "ISS a Recuperar", notas.md 2026-07-15i/j).
SIGLAS_TRIBUTOS = {
    "INSS", "IRRF", "IR", "ISS", "ISSQN", "FGTS", "PIS", "PASEP", "COFINS",
    "CSLL", "CSRF", "ICMS", "IPI", "INCRA", "SENAI", "SENAC", "SESI", "SESC", "SEBRAE",
}

CONFIANCA_MINIMA = 0.6
# Abaixo deste valor, um match de rubrica por nome aproximado (não exato, não
# por código eSocial) ainda é usado, mas cai em "revisar_match_rubrica" em vez
# de aprovar sozinho. A pedido do Robert (2026-09-11): aprovação automática
# pra tudo que bater 80% ou mais (era 85%).
CONFIANCA_MINIMA_NOME_APROXIMADO = 0.80

SITUACOES = (
    "ok",
    "informativa_sem_contabilizacao",
    "sem_conta_para_natureza",
    "revisar_conta_empresa",
    "revisar_match_rubrica",
    "sem_match_bhub",
)


def _normalizar_texto(texto):
    texto = (texto or "").upper().strip()
    texto = re.sub(r"[^A-Z0-9 ]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _siglas_tributo(nome):
    tokens = set(_normalizar_texto(nome).split())
    return tokens & SIGLAS_TRIBUTOS


def _similaridade(a_norm, b_norm):
    return SequenceMatcher(None, a_norm, b_norm).ratio()


def _construir_indice_tokens(itens_normalizados):
    """itens_normalizados: lista de (nome_normalizado, item). Devolve um dict
    token -> [(nome_normalizado, item), ...], usado para restringir a comparação
    fuzzy só a candidatas que compartilham pelo menos uma palavra com a consulta —
    comparar contra TODAS as candidatas com SequenceMatcher fica caro demais em
    listas de milhares de itens (ex.: 2611 rubricas x 2381 candidatas BHub)."""
    indice = {}
    for nome_norm, item in itens_normalizados:
        for token in nome_norm.split():
            indice.setdefault(token, []).append((nome_norm, item))
    return indice


def _candidatas_por_token(nome_consulta_norm, indice_tokens, todas):
    vistas = {}
    for token in nome_consulta_norm.split():
        for nome_norm, item in indice_tokens.get(token, ()):
            vistas[id(item)] = (nome_norm, item)
    if vistas:
        return vistas.values()
    return todas  # sem palavra em comum: cai pro conjunto completo (já deve ser pequeno)


def construir_indice_contas_empresa(contas_empresa):
    """Agrupa as contas analíticas da empresa por natureza contábil (ativo/passivo/
    receita/despesa), com índice de tokens por natureza, para acelerar match_conta."""
    por_natureza = {}
    for conta in contas_empresa:
        if conta.tipo_cta != "A":
            continue
        por_natureza.setdefault(conta.natureza, []).append(conta)

    indice = {}
    for natureza, contas in por_natureza.items():
        normalizadas = [(_normalizar_texto(c.nome), c) for c in contas]
        indice[natureza] = {
            "normalizadas": normalizadas,
            "tokens": _construir_indice_tokens(normalizadas),
        }
    return indice


def match_conta(codigo_conta_bhub, plano_contas_bhub, indice_contas_empresa):
    """Acha, no plano de contas da empresa, a conta equivalente a uma conta BHub.

    `indice_contas_empresa` vem de construir_indice_contas_empresa() — filtra
    candidatas pela MESMA natureza (ativo/passivo/receita/despesa) e exclui
    qualquer candidata cuja sigla de tributo seja diferente da sigla da conta BHub
    (mesmo com texto parecido). Devolve (ContaEmpresa | None, confiança 0-1)."""
    conta_bhub = plano_contas_bhub.get(codigo_conta_bhub)
    if conta_bhub is None:
        return None, 0.0

    bucket = indice_contas_empresa.get(conta_bhub.natureza)
    if not bucket:
        return None, 0.0

    siglas_bhub = _siglas_tributo(conta_bhub.nome)
    nome_bhub_norm = _normalizar_texto(conta_bhub.nome)
    candidatas = _candidatas_por_token(nome_bhub_norm, bucket["tokens"], bucket["normalizadas"])

    melhor, melhor_score = None, 0.0
    for nome_norm, candidata in candidatas:
        siglas_candidata = _siglas_tributo(candidata.nome)
        if siglas_candidata != siglas_bhub and (siglas_candidata or siglas_bhub):
            continue
        score = _similaridade(nome_bhub_norm, nome_norm)
        if score > melhor_score:
            melhor, melhor_score = candidata, score

    return melhor, melhor_score


def construir_indice_rubricas_bhub(rubricas_bhub_do_tipo):
    """Índice por nome exato, por código eSocial e por token, para acelerar
    match_rubrica quando há milhares de rubricas dos dois lados."""
    normalizadas = [(_normalizar_texto(r.nome), r) for r in rubricas_bhub_do_tipo]
    exato = {}
    for nome_norm, r in normalizadas:
        exato.setdefault(nome_norm, r)
    por_esocial = {}
    for r in rubricas_bhub_do_tipo:
        if r.codigo_esocial:
            por_esocial.setdefault(r.codigo_esocial, r)
    return {
        "exato": exato,
        "esocial": por_esocial,
        "normalizadas": normalizadas,
        "tokens": _construir_indice_tokens(normalizadas),
    }


def match_rubrica(rubrica_empresa, indice_rubricas_bhub):
    """Equivalência de rubrica: nome exato -> código eSocial -> nome aproximado.
    `indice_rubricas_bhub` vem de construir_indice_rubricas_bhub(). Devolve
    (RubricaBhub | None, metodo, confiança)."""
    nome_empresa_norm = _normalizar_texto(rubrica_empresa.nome)

    encontrada = indice_rubricas_bhub["exato"].get(nome_empresa_norm)
    if encontrada is not None:
        return encontrada, "nome_exato", 1.0

    if rubrica_empresa.codigo_esocial:
        encontrada = indice_rubricas_bhub["esocial"].get(rubrica_empresa.codigo_esocial)
        if encontrada is not None:
            return encontrada, "codigo_esocial", 0.9

    candidatas = _candidatas_por_token(
        nome_empresa_norm, indice_rubricas_bhub["tokens"], indice_rubricas_bhub["normalizadas"]
    )

    melhor, melhor_score = None, 0.0
    for nome_norm, candidata in candidatas:
        score = _similaridade(nome_empresa_norm, nome_norm)
        if score > melhor_score:
            melhor, melhor_score = candidata, score

    if melhor is not None and melhor_score >= CONFIANCA_MINIMA:
        return melhor, "nome_aproximado", melhor_score
    return None, "sem_match", 0.0


def classificar_situacao(
    rubrica_bhub,
    metodo_match,
    confianca_match,
    natureza_empresa,
    conta_debito_empresa,
    confianca_debito,
    conta_credito_empresa,
    confianca_credito,
):
    """Devolve uma das SITUACOES para orientar a revisão na tela."""
    if rubrica_bhub is None:
        return "sem_match_bhub"

    if rubrica_bhub.natureza in ("I", "ID") and not rubrica_bhub.contas:
        # Informativa pro eSocial/cálculo interno, sem lançamento contábil no padrão
        # BHub em nenhuma natureza — não deve ser cadastrada (não é pendência).
        return "informativa_sem_contabilizacao"

    if natureza_empresa not in rubrica_bhub.contas:
        return "sem_conta_para_natureza"

    if metodo_match == "nome_aproximado" and confianca_match < CONFIANCA_MINIMA_NOME_APROXIMADO:
        return "revisar_match_rubrica"

    if conta_debito_empresa is None or conta_credito_empresa is None:
        return "revisar_conta_empresa"

    if confianca_debito < CONFIANCA_MINIMA or confianca_credito < CONFIANCA_MINIMA:
        return "revisar_conta_empresa"

    return "ok"
