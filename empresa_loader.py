"""Lê o plano de contas e a relação de rubricas exportados do Domínio por uma
empresa fora do padrão BHub (.xls BIFF2 antigo ou .xlsx).

Reconstruído em 2026-08-19 a partir de notas.md — os nomes de coluna abaixo
(codi_cta/clas_cta/tipo_cta/nome_cta para o plano de contas; i_eventos/codi_emp/
nome/codigo_esocial para a relação de rubricas) foram confirmados no piloto
original com a empresa Nova Rede.
"""

from dataclasses import dataclass

import pandas as pd

from bhub_model import derivar_natureza_por_nome


@dataclass
class ContaEmpresa:
    codigo: str
    nome: str
    clas_cta: str
    tipo_cta: str  # "A" analítica / "S" sintética
    natureza: str = "desconhecida"


@dataclass
class RubricaEmpresa:
    codigo: str  # i_eventos — código da rubrica no catálogo da própria empresa
    nome: str
    codigo_esocial: str
    codi_emp: str


def _ler_planilha(caminho, **kwargs):
    """`caminho` pode ser um caminho de arquivo (str/Path, uso via CLI) ou um
    arquivo enviado pelo Streamlit (`UploadedFile`, uso via streamlit_app.py).
    Bug real corrigido em 2026-08-21: `str(caminho)` transformava o objeto de
    upload na sua representação tipo "UploadedFile(file_id=...)" e essa string
    virava o "caminho" passado pro pandas — dava FileNotFoundError, porque não
    existe arquivo nenhum com esse nome no disco. Usar `.name` só pra decidir o
    engine, e passar o objeto original (arquivo-like) pro pandas."""
    nome = getattr(caminho, "name", caminho)
    engine = "xlrd" if str(nome).lower().endswith(".xls") else "openpyxl"
    return pd.read_excel(caminho, engine=engine, **kwargs)


def _normalizar_colunas(df):
    return df.rename(columns={c: str(c).strip().lower() for c in df.columns})


def _str_numero(valor):
    if pd.isna(valor):
        return ""
    texto = str(valor).strip()
    if texto.endswith(".0"):
        texto = texto[:-2]
    return texto


def carregar_plano_contas_empresa(caminho):
    df = _normalizar_colunas(_ler_planilha(caminho))
    contas = []
    for _, linha in df.iterrows():
        codigo = _str_numero(linha.get("codi_cta"))
        if not codigo:
            continue
        contas.append(ContaEmpresa(
            codigo=codigo,
            nome=str(linha.get("nome_cta") or "").strip(),
            clas_cta=str(linha.get("clas_cta") or "").strip(),
            tipo_cta=str(linha.get("tipo_cta") or "").strip().upper(),
        ))
    _classificar_natureza_por_grupo_topo(contas)
    return contas


def _classificar_natureza_por_grupo_topo(contas):
    """Natureza da conta (ativo/passivo/receita/despesa) vem do nome do grupo de
    NÍVEL 1 do plano da própria empresa — o dígito inicial da classificação
    hierárquica não é comparável entre empresas (achado de notas.md 2026-07-14c)."""
    sinteticas = [c for c in contas if c.tipo_cta == "S" and c.clas_cta]
    for conta in contas:
        ancestrais = [
            s for s in sinteticas
            if s is not conta and conta.clas_cta.startswith(s.clas_cta)
        ]
        grupo_topo = min(ancestrais, key=lambda s: len(s.clas_cta), default=None)
        nome_referencia = grupo_topo.nome if grupo_topo else conta.nome
        conta.natureza = derivar_natureza_por_nome(nome_referencia)


def carregar_rubricas_empresa(caminho):
    df = _normalizar_colunas(_ler_planilha(caminho))
    rubricas = []
    for _, linha in df.iterrows():
        codigo = _str_numero(linha.get("i_eventos"))
        if not codigo:
            continue
        rubricas.append(RubricaEmpresa(
            codigo=codigo,
            nome=str(linha.get("nome") or "").strip(),
            codigo_esocial=_str_numero(linha.get("codigo_esocial")),
            codi_emp=_str_numero(linha.get("codi_emp")),
        ))
    return rubricas
