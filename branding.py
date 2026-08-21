"""Identidade visual BHub aplicada ao app, com base no "Manual da Marca BHub -
Outubro 2025.pdf" (salvo na pasta do projeto).

Cuidado que já causou um bug real (notas.md 2026-07-15m): st.markdown() segue as
regras do Markdown/CommonMark — qualquer linha com 4+ espaços de indentação vira
bloco de código (aparece como texto cru, sem renderizar). Toda string HTML/CSS
abaixo passa por _sem_indentacao() antes de ir pro st.markdown().

Reconstruído em 2026-08-19 a partir de notas.md.
"""

import streamlit as st

CORES = {
    "bushido_night": "#0F1727",
    "sensei_glow": "#F9F9F9",
    "samurai_black": "#141414",
    "dojo_steel": "#3D3D3D",
    "karesansui_sand": "#E1DCCC",
    "mizu_flow": "#0171E4",
    "coral_hikari": "#F25461",
}


def _sem_indentacao(texto):
    return "\n".join(linha.strip() for linha in texto.strip().splitlines())


def _logo_mark_html(tamanho=32):
    lado = round(tamanho * 0.32)
    return _sem_indentacao(f"""
    <div style="display:flex; gap:2px; justify-content:center; align-items:center;">
      <span style="width:{lado}px; height:{lado}px; background:{CORES['sensei_glow']}; transform:rotate(45deg); display:inline-block;"></span>
      <span style="width:{lado}px; height:{lado}px; background:{CORES['sensei_glow']}; transform:rotate(45deg); display:inline-block;"></span>
      <span style="width:{lado}px; height:{lado}px; background:{CORES['sensei_glow']}; transform:rotate(45deg); display:inline-block;"></span>
    </div>
    """)


def aplicar_tema_bhub():
    st.markdown(_sem_indentacao(f"""
    <link href="https://fonts.googleapis.com/css2?family=Lato:wght@400;700;900&display=swap" rel="stylesheet">
    <style>
    html, body, [class*="css"] {{
        font-family: 'Lato', sans-serif;
    }}
    section[data-testid="stSidebar"] {{
        background-color: {CORES['bushido_night']};
    }}
    section[data-testid="stSidebar"] * {{
        color: {CORES['sensei_glow']};
    }}
    section[data-testid="stSidebar"] [data-testid="stAlert"] * {{
        color: {CORES['samurai_black']} !important;
    }}
    /* Bug real corrigido em 2026-08-21: a regra acima ("*") também forçava
       branco dentro dos campos de texto/número/seletor — que têm fundo claro
       próprio (do tema base do Streamlit) — deixando o que o Robert digitava
       invisível (texto branco em campo branco). Estes seletores devolvem o
       texto pra escuro só dentro da caixa do campo, sem afetar o rótulo (que
       continua branco, sobre o fundo escuro da barra lateral). */
    section[data-testid="stSidebar"] input,
    section[data-testid="stSidebar"] textarea,
    section[data-testid="stSidebar"] [data-baseweb="select"] * {{
        color: {CORES['samurai_black']} !important;
    }}
    .stButton > button {{
        background-color: {CORES['mizu_flow']};
        color: {CORES['sensei_glow']};
        border: none;
    }}
    </style>
    """), unsafe_allow_html=True)


def cabecalho_bhub(titulo):
    st.markdown(_sem_indentacao(f"""
    <div style="display:flex; align-items:center; gap:12px; margin-bottom:8px;">
      {_logo_mark_html(40)}
      <h1 style="font-weight:900; margin:0;">{titulo}<span style="color:{CORES['coral_hikari']};">.</span></h1>
    </div>
    """), unsafe_allow_html=True)


def cabecalho_sidebar_bhub():
    st.sidebar.markdown(_sem_indentacao(f"""
    <div style="display:flex; flex-direction:column; align-items:center; gap:6px; padding:12px 0 20px 0;">
      {_logo_mark_html(28)}
      <span style="font-weight:900; letter-spacing:1px;">BHub</span>
    </div>
    """), unsafe_allow_html=True)


def secao_sidebar_bhub(icone, titulo):
    st.sidebar.markdown(_sem_indentacao(f"""
    <div style="text-align:center; margin:16px 0 8px 0;">
      <div style="font-size:20px;">{icone}</div>
      <div style="font-size:12px; letter-spacing:1px; text-transform:uppercase;">{titulo}</div>
    </div>
    """), unsafe_allow_html=True)


def texto_sidebar_bhub(texto):
    st.sidebar.markdown(_sem_indentacao(f"""
    <p style="color:{CORES['karesansui_sand']}; font-size:12px;">{texto}</p>
    """), unsafe_allow_html=True)


def formatar_tempo(segundos):
    segundos = int(segundos)
    if segundos < 60:
        return f"{segundos}s"
    minutos, resto = divmod(segundos, 60)
    return f"{minutos}min {resto}s"
