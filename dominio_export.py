"""Gera EVENTO.txt e INTEGRA.txt no layout de importação do Domínio.

Layout confirmado campo a campo pelo Robert (notas.md 2026-07-15e/f, 2026-07-16a-d):

EVENTO (9 campos): empresa; lançamento (sequencial próprio); Tipo da Integração
(1 Folha/2 Empresa/3 Férias/4 Rescisão/5 Prov.Férias/6 Prov.13); descrição;
CRÉDITO; DÉBITO (nessa ordem); histórico; departamento; "1" fixo.

INTEGRA (6 campos): empresa; lançamento (mesmo valor do campo 2 do EVENTO);
Tipo da Integração; código da rubrica da empresa (i_eventos); departamento;
"1" fixo.

Empresa e CNPJ são fixos pro processo inteiro. Departamento, Tipo da Integração
e a numeração de histórico/lançamento são por TRATATIVA (departamento) — um
mesmo processo pode gerar rubricas de vários departamentos diferentes, cada um
com sua própria sequência de histórico/lançamento (2026-08-21, a pedido do
Robert). Ver `tratativa.py`.

Reconstruído em 2026-08-19 a partir de notas.md.
"""

from dataclasses import dataclass


@dataclass
class LinhaResolvida:
    descricao: str
    conta_debito_empresa: str
    conta_credito_empresa: str
    codigo_rubrica_empresa: str
    tipo_rubrica_bhub: str
    natureza_rubrica: str
    numero_rubrica_bhub: str
    tratativa_id: str
    departamento: str
    tipo_integracao: int
    numero_historico: str = ""
    numero_lancamento: str = ""


def _fmt(valor):
    if valor is None:
        return ""
    texto = str(valor).strip()
    if texto.endswith(".0"):
        texto = texto[:-2]
    return texto


def gerar_arquivos_dominio(linhas, codigo_empresa, numeracao_por_tratativa):
    """Numera histórico e lançamento sequencialmente (+1 por linha, a partir do
    ÚLTIMO número já cadastrado NAQUELA tratativa/departamento — não um contador
    global compartilhado entre departamentos) e gera os dois arquivos.

    `numeracao_por_tratativa`: {tratativa_id: {"ultimo_historico": int,
    "ultimo_lancamento": int}} — um bloco de numeração por departamento.

    Devolve (evento_txt, integra_txt, linhas_numeradas). As linhas de saída
    seguem a ordem de `linhas` (isto é, a ordem em que os departamentos foram
    adicionados no processo)."""
    contadores = {
        tid: dict(valores) for tid, valores in numeracao_por_tratativa.items()
    }
    evento_linhas, integra_linhas = [], []

    for linha in linhas:
        estado = contadores[linha.tratativa_id]
        estado["ultimo_historico"] += 1
        estado["ultimo_lancamento"] += 1
        linha.numero_historico = _fmt(estado["ultimo_historico"])
        linha.numero_lancamento = _fmt(estado["ultimo_lancamento"])

        evento_linhas.append(";".join([
            _fmt(codigo_empresa),
            linha.numero_lancamento,
            _fmt(linha.tipo_integracao),
            linha.descricao,
            _fmt(linha.conta_credito_empresa),
            _fmt(linha.conta_debito_empresa),
            linha.numero_historico,
            _fmt(linha.departamento),
            "1",
        ]))

        integra_linhas.append(";".join([
            _fmt(codigo_empresa),
            linha.numero_lancamento,
            _fmt(linha.tipo_integracao),
            _fmt(linha.codigo_rubrica_empresa),
            _fmt(linha.departamento),
            "1",
        ]))

    return "\n".join(evento_linhas), "\n".join(integra_linhas), linhas
