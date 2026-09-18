"""Gera EVENTO.txt e INTEGRA.txt no layout de importação do Domínio.

Layout confirmado campo a campo pelo Robert (notas.md 2026-07-15e/f, 2026-07-16a-d):

EVENTO (9 campos): empresa; lançamento (sequencial próprio); Tipo da Integração
(1 Folha/2 Empresa/3 Férias/4 Rescisão/5 Prov.Férias/6 Prov.13); descrição;
CRÉDITO; DÉBITO (nessa ordem); histórico; departamento; "1" fixo.

INTEGRA (6 campos): empresa; lançamento (mesmo valor do campo 2 do EVENTO);
Tipo da Integração; código da rubrica da empresa (i_eventos); departamento;
"1" fixo.

Empresa e CNPJ são fixos pro processo inteiro. Departamento e Tipo da
Integração são por TRATATIVA (departamento) — um mesmo processo pode gerar
rubricas de vários departamentos diferentes. Ver `tratativa.py`.

Numeração de LANÇAMENTO: por tratativa, cada uma com sua própria sequência
(2026-08-21, a pedido do Robert) — não muda com a regra abaixo.

Numeração de HISTÓRICO: **compartilhada entre departamentos** (2026-09-18, a
pedido do Robert) — o histórico descreve a RUBRICA, não o departamento, então
a mesma rubrica usada em departamentos diferentes tem que cair no MESMO
número de histórico (dedup pelo texto formatado do histórico — ver
`montar_descricao_historico` em historico_export.py). Só quando o texto é
inédito é que se cria um número novo, continuando a sequência — não reinicia
por departamento. O contador começa em `ultimo_historico + 1` do PRIMEIRO
departamento cadastrado no processo (ver `novo_estado_historico`).

Reconstruído em 2026-08-19 a partir de notas.md.
"""

from dataclasses import dataclass

import historico_export


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


def novo_estado_historico(numeracao_por_tratativa):
    """Cria o estado do contador GLOBAL de histórico (compartilhado entre
    departamentos), semeado a partir do `ultimo_historico` do PRIMEIRO
    departamento cadastrado no processo — `numeracao_por_tratativa` é um dict
    e preserva a ordem de inserção (a ordem em que os departamentos foram
    adicionados em `st.session_state.departamentos`).

    Chamar uma vez só por exportação (não por chamada de
    `gerar_arquivos_dominio`) e passar o mesmo objeto adiante quando a
    exportação faz várias chamadas em sequência (ex.: modo "separado", um
    arquivo por departamento) — assim o contador e o reaproveitamento por
    texto continuam entre as chamadas em vez de reiniciar a cada
    departamento."""
    primeiro = next(iter(numeracao_por_tratativa.values()), {"ultimo_historico": 0})
    return {"proximo": primeiro["ultimo_historico"] + 1, "por_texto": {}}


def gerar_arquivos_dominio(linhas, codigo_empresa, numeracao_por_tratativa, estado_historico):
    """Numera lançamento sequencialmente (+1 por linha, a partir do ÚLTIMO
    número já cadastrado NAQUELA tratativa/departamento — contador
    independente por departamento) e histórico a partir de `estado_historico`
    (contador GLOBAL, compartilhado entre departamentos — mesma rubrica em
    departamentos diferentes reaproveita o mesmo número; ver
    `novo_estado_historico`). Gera os dois arquivos.

    `numeracao_por_tratativa`: {tratativa_id: {"ultimo_historico": int,
    "ultimo_lancamento": int}} — usado só pra semear lançamento aqui (o
    `ultimo_historico` de cada tratativa já foi consumido em
    `novo_estado_historico`).

    Devolve (evento_txt, integra_txt, linhas_numeradas, estado_historico) —
    devolve o MESMO objeto `estado_historico` recebido (mutado in-place),
    pra encadear em chamadas seguintes. As linhas de saída seguem a ordem de
    `linhas` (isto é, a ordem em que os departamentos foram adicionados no
    processo)."""
    contadores = {
        tid: dict(valores) for tid, valores in numeracao_por_tratativa.items()
    }
    evento_linhas, integra_linhas = [], []

    for linha in linhas:
        estado = contadores[linha.tratativa_id]
        estado["ultimo_lancamento"] += 1
        linha.numero_lancamento = _fmt(estado["ultimo_lancamento"])

        descricao_historico, _confirmado = historico_export.montar_descricao_historico(linha)
        numero_ja_usado = estado_historico["por_texto"].get(descricao_historico)
        if numero_ja_usado is not None:
            linha.numero_historico = numero_ja_usado
        else:
            linha.numero_historico = _fmt(estado_historico["proximo"])
            estado_historico["por_texto"][descricao_historico] = linha.numero_historico
            estado_historico["proximo"] += 1

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

    return "\n".join(evento_linhas), "\n".join(integra_linhas), linhas, estado_historico
