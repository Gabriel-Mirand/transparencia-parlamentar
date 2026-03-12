# ==========================================================
# IMPORTS
# ==========================================================
import streamlit as st
import pandas as pd
import psycopg2
import plotly.express as px
import numpy as np
import os
from dotenv import load_dotenv

# ==========================================================
# CONFIGURAÇÃO DA PÁGINA
# ==========================================================
st.set_page_config(page_title="Transparência Parlamentar", layout="wide")

st.title("📊 Transparência de Gastos Parlamentares")
st.markdown("Como o seu deputado tem gasto a cota parlamentar?")
st.markdown("Os gráficos abaixo apresentam uma visão geral dos gastos parlamentares. Para realizar comparativos e visualizar detalhes específicos, selecione os deputados na barra lateral.")

# ==========================================================
# CARREGAMENTO E TRATAMENTO (SÓ RODA UMA VEZ)
# ==========================================================

try:
    df = carregar_dados()
    
    # --- TRATAMENTO INICIAL (Essencial para os filtros de tempo) ---
    df["data"] = pd.to_datetime(df["data"])
    df["valor"] = pd.to_numeric(df["valor"])
    df["mes_ano"] = df["data"].dt.to_period("M").astype(str)
    df["deputado_partido"] = df["nome"] + " (" + df["partido"] + ")"

    # ==========================================================
    # SIDEBAR - FILTRO DE TEMPO (O ÚNICO QUE AFETA A INTRODUÇÃO)
    # ==========================================================
    st.sidebar.header("📅 Período de Análise")
    periodos = sorted(df["mes_ano"].unique())
    periodo_inicio = st.sidebar.selectbox("Início", periodos, index=0)
    periodo_fim = st.sidebar.selectbox("Fim", periodos, index=len(periodos)-1)

    # Base da Câmara filtrada APENAS pelo tempo
    df_camera_total = df[(df["mes_ano"] >= periodo_inicio) & (df["mes_ano"] <= periodo_fim)]

    # ==========================================================
    # 🏛️ 1. GASTO TOTAL DA CÂMARA (APARECE DE CARA)
    # ==========================================================
    st.header("🏛️ Visão Geral da Câmara")
    
    total_camera = df_camera_total["valor"].sum()
    qtd_notas = len(df_camera_total)
    
    c1, c2 = st.columns(2)
    c1.metric("Total Gasto pela Câmara", f"R$ {total_camera:,.2f}")
    c2.metric("Total de Notas Fiscais", f"{qtd_notas:,}".replace(",", "."))
    
    st.divider()

    # ==========================================================
    # 🏆 2. PARTIDO CAMPEÃO E MÉDIAS (APARECE DE CARA)
    # ==========================================================
    st.subheader("🏆 Gastos por Partido")
    
    # Cálculos por Partido
    total_partido = df_camera_total.groupby("partido")["valor"].sum()
    deps_partido = df_camera_total.groupby("partido")["nome"].nunique()
    
    ranking_p = pd.DataFrame({"total": total_partido, "deps": deps_partido}).reset_index()
    ranking_p["media"] = ranking_p["total"] / ranking_p["deps"]
    ranking_p = ranking_p.sort_values("total", ascending=False)

    fig_p = px.bar(ranking_p, x="partido", y="total", title="Total por Partido", color="partido")
    st.plotly_chart(fig_p, use_container_width=True)

    fig_m = px.bar(ranking_p.sort_values("media", ascending=False), x="partido", y="media", 
                   title="Média de Gasto por Deputado no Partido", color_discrete_sequence=['#FFA500'])
    st.plotly_chart(fig_m, use_container_width=True)

    st.divider()

    # ==========================================================
    # 🥇 3. TOP 3 DEPUTADOS NACIONAL (APARECE DE CARA)
    # ==========================================================
    st.subheader("🥇 Top 3 Deputados que Mais Gastaram (Nacional)")
    
    top3 = df_camera_total.groupby(["nome", "partido"])["valor"].sum().sort_values(ascending=False).head(3).reset_index()
    
    cols_t3 = st.columns(3)
    meds = ["🥇", "🥈", "🥉"]
    for i, row in top3.iterrows():
        cols_t3[i].metric(label=f"{meds[i]} {row['nome']}", 
                          value=f"R$ {row['valor']:,.2f}", 
                          delta=row['partido'], delta_color="off")

    st.divider()

    # ==========================================================
    # 🛑 MENSAGEM DE INSTRUÇÃO E PONTO DE PARADA
    # ==========================================================
    st.info("💡 **Aprofunde sua busca:** Os dados acima são gerais da Câmara. Use o menu lateral para selecionar deputados e ver detalhes individuais, evolução e notas fiscais.")

    # Filtro de Deputados na Sidebar
    deputados_sel = st.sidebar.multiselect(
        "Selecione Deputados para Detalhar:", 
        options=sorted(df_camera_total["deputado_partido"].unique())
    )

    if not deputados_sel:
        st.stop() # O dashboard para aqui se ninguém for selecionado

    # ==========================================================
    # 📊 4. DETALHAMENTO INDIVIDUAL (SÓ RODA SE SELECIONAR)
    # ==========================================================
    df_filtrado = df_camera_total[df_camera_total["deputado_partido"].isin(deputados_sel)]
    
    # ... (Aqui você coloca os blocos de Evolução Mensal, Distribuição e Tabela Final) ...

except Exception as e:
    st.error(f"Erro ao carregar dashboard: {e}")
    st.stop()

# ==========================================================
# SIDEBAR — FILTROS
# ==========================================================
st.sidebar.header("🔎 Filtros")

# ==========================================================
# FILTRO DE PERÍODO (MÊS / ANO)
# ==========================================================

# Garantir que a coluna data está no formato datetime
df["data"] = pd.to_datetime(df["data"])

# Criar coluna mês/ano
df["mes_ano"] = df["data"].dt.to_period("M").astype(str)

periodos = sorted(df["mes_ano"].unique())

st.sidebar.subheader("📅 Intervalo de Tempo")

periodo_inicio = st.sidebar.selectbox(
    "Mês/Ano inicial",
    periodos,
    index=0
)

periodo_fim = st.sidebar.selectbox(
    "Mês/Ano final",
    periodos,
    index=len(periodos) - 1
)

df = df[
    (df["mes_ano"] >= periodo_inicio) &
    (df["mes_ano"] <= periodo_fim)
]

# ==========================================================
# FILTRO POR PARTIDO
# ==========================================================

partidos = sorted(df["partido"].dropna().unique())

partido_selecionado = st.sidebar.multiselect(
    "Filtrar por Partido",
    partidos,
    default=partidos
)

df = df[df["partido"].isin(partido_selecionado)]

# ==========================================================
# FILTRO POR DEPUTADO
# ==========================================================

deputados = sorted(df["deputado_partido"].unique())

deputados_selecionados = st.sidebar.multiselect(
    "Selecione até 5 deputados",
    deputados,
    max_selections=5
)

if not deputados_selecionados:
    st.warning("Selecione pelo menos um deputado.")
    st.stop()

df_filtrado = df[df["deputado_partido"].isin(deputados_selecionados)]

# ==========================================================
# FILTRO POR TIPO DE GASTO
# ==========================================================

tipos_gasto = sorted(df_filtrado["descricao"].unique())

tipo_selecionado = st.sidebar.multiselect(
    "Filtrar por Tipo de Gasto",
    tipos_gasto,
    default=tipos_gasto
)

df_filtrado = df_filtrado[df_filtrado["descricao"].isin(tipo_selecionado)]

# ==========================================================
# FILTRO POR VALOR MÍNIMO
# ==========================================================

valor_min = st.sidebar.number_input(
    "Valor mínimo do gasto",
    min_value=0.0,
    value=0.0
)

df_filtrado = df_filtrado[df_filtrado["valor"] >= valor_min]

# ==========================================================
# BUSCA TEXTUAL NA DESCRIÇÃO
# ==========================================================

busca = st.sidebar.text_input("Buscar palavra na descrição")

if busca:
    df_filtrado = df_filtrado[
        df_filtrado["descricao"].str.contains(busca, case=False, na=False)
    ]
# ==========================================================
# 🔗 FONTE DOS DADOS
# ==========================================================
st.sidebar.markdown("---")
st.sidebar.markdown("### 🔎 Fonte dos Dados")

st.sidebar.markdown(
    """
    Dados coletados da API oficial da  
    [Câmara dos Deputados](https://dadosabertos.camara.leg.br/)

    Portal de Dados Abertos do Governo Federal.
    """
)

st.sidebar.markdown("---")
st.sidebar.markdown("Dashboard Versão 1.0")

# ==========================================================
# 📊 COMPARAÇÃO E DISTRIBUIÇÃO (POR DEPUTADO SELECIONADO)
# ==========================================================
st.subheader("📊 Análise dos Deputados Selecionados")

# --- NOVIDADE: Criar o mapa de cores fixo para todos os tipos de gastos ---
todas_descricoes = sorted(df["descricao"].unique())
cores_disponiveis = px.colors.qualitative.Alphabet # Paleta com muitas cores
mapa_cores_fixo = {desc: cores_disponiveis[i % len(cores_disponiveis)] for i, desc in enumerate(todas_descricoes)}
mapa_cores_fixo["Outros"] = "#808080" # Cinza para o grupo Outros
# --------------------------------------------------------------------------

comparacao = df_filtrado.groupby("deputado_partido")["valor"].sum().reset_index()

fig_comp = px.bar(comparacao, x="deputado_partido", y="valor", title="Comparativo de Gastos")
st.plotly_chart(fig_comp, use_container_width=True)

# Gastos por Tipo (Pie Charts)
for deputado in df_filtrado["deputado_partido"].unique():
    with st.expander(f"🔍 Ver detalhes de: {deputado}"):
        df_dep = df_filtrado[df_filtrado["deputado_partido"] == deputado]
        gasto_tipo = df_dep.groupby("descricao")["valor"].sum().reset_index()
        
        # Agrupar menores que 2%
        total_dep = gasto_tipo["valor"].sum()
        gasto_tipo["pct"] = (gasto_tipo["valor"] / total_dep) * 100
        maiores = gasto_tipo[gasto_tipo["pct"] >= 2].copy() # .copy() evita avisos do pandas
        outros_val = gasto_tipo[gasto_tipo["pct"] < 2]["valor"].sum()
        
        if outros_val > 0:
            novo_item = pd.DataFrame([{"descricao": "Outros", "valor": outros_val}])
            maiores = pd.concat([maiores, novo_item], ignore_index=True)
        
        # AJUSTE NO GRÁFICO: Adicionamos color e color_discrete_map
        fig_pie = px.pie(
            maiores, 
            names="descricao", 
            values="valor", 
            title=f"Distribuição: {deputado}",
            color="descricao",
            color_discrete_map=mapa_cores_fixo
        )
        
        # Melhora a legenda para não ficar cortada no celular
        fig_pie.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.5))
        
        st.plotly_chart(fig_pie, use_container_width=True)

st.divider()

# ==========================================================
# 📈 EVOLUÇÃO MENSAL (RESPONSIVO)
# ==========================================================
st.subheader("📈 Evolução Mensal")

# Agrupamento para o gráfico de linhas
mensal = (
    df_filtrado.groupby(["mes", "deputado_partido"])["valor"]
    .sum()
    .reset_index()
)

fig_linha = px.line(
    mensal,
    x="mes",
    y="valor",
    color="deputado_partido",
    markers=True,
    labels={"mes": "Mês", "valor": "Total Gasto (R$)", "deputado_partido": "Deputado"},
    title="Gastos ao longo do tempo"
)

# use_container_width garante que o gráfico não "estoure" a tela do celular
st.plotly_chart(fig_linha, use_container_width=True)
st.divider()

# ==========================================================
# ⚠️ GASTOS MUITO ACIMA DA MÉDIA (BASE COMPLETA)
# ==========================================================
st.subheader("⚠️ Alertas: Gastos Fora do Padrão")

# Média da base COMPLETA (todos os deputados no período)
media_geral = df["valor"].mean()
limite = media_geral * 5

# Exibição em métricas para facilitar leitura no celular
col_m1, col_m2 = st.columns(2)
col_m1.metric("Média Geral por Nota", f"R$ {media_geral:,.2f}")
col_m2.metric("Limite p/ Alerta (5x)", f"R$ {limite:,.2f}")

st.markdown(f"🔎 Analisando gastos acima de **R$ {limite:,.2f}** no filtro atual.")

acima_media = df_filtrado[df_filtrado["valor"] > limite]

if not acima_media.empty:
    st.warning(f"🚨 Detectados {len(acima_media)} gastos muito acima da média.")
    
    # Tabela simplificada para o celular (formatada)
    st.dataframe(
        acima_media[["data", "nome", "valor", "descricao"]].sort_values("valor", ascending=False),
        use_container_width=True,
        hide_index=True,
        column_config={
            "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
            "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f")
        }
    )
else:
    st.success("✅ Nenhum gasto muito acima da média encontrado nos filtros atuais.")

st.divider()

# ==========================================================
# 🏆 RANKING DE GASTOS ATÍPICOS (ACIMA DA MÉDIA)
# ==========================================================
st.subheader("🏆 Ranking de Deputados com Mais Gastos Acima da Média")

if not acima_media.empty:
    ranking_acima = (
        acima_media
        .groupby(["nome", "partido"])
        .agg(
            qtd_ocorrencias=("valor", "count"),
            total_acima=("valor", "sum")
        )
        .reset_index()
        .sort_values(by="qtd_ocorrencias", ascending=False)
    )

    # PEGA OS TOP 3
    top_3 = ranking_acima.head(3)
    
    # CRIA AS COLUNAS DINAMICAMENTE (Evita o IndexError)
    num_cols = len(top_3)
    if num_cols > 0:
        r_cols = st.columns(num_cols)
        medalhas = ["🥇", "🥈", "🥉"]

        for i, (index, row) in enumerate(top_3.iterrows()):
            with r_cols[i]:
                st.metric(
                    label=f"{medalhas[i]} {row['nome']}", 
                    value=f"{row['qtd_ocorrencias']} notas",
                    delta=f"R$ {row['total_acima']:,.0f} total",
                    delta_color="inverse" 
                )

    with st.expander("📊 Ver ranking completo de anomalias"):
        st.dataframe(ranking_acima, use_container_width=True, hide_index=True)
else:
    st.info("Nenhum dado atípico para gerar ranking.")

st.divider()

# ==========================================================
# 📄 TABELA FINAL FORMATADA (MUITO MELHOR NO CELULAR)
# ==========================================================
st.subheader("📄 Lista Completa de Gastos")

st.dataframe(
    df_filtrado[["data", "nome", "partido", "valor", "descricao"]].sort_values("data", ascending=False),
    use_container_width=True,
    hide_index=True,
    column_config={
        "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
        "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
        "nome": "Deputado",
        "descricao": "Descrição"
    }
)










