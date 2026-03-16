# ==========================================================
# IMPORTS
# ==========================================================
import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

# ==========================================================
# CONFIGURAÇÃO DA PÁGINA
# ==========================================================
st.set_page_config(page_title="Transparência Parlamentar", layout="wide")

st.title("📊 Transparência de Gastos Parlamentares")
st.markdown("Acompanhe como a cota parlamentar está sendo utilizada.")

# ==========================================================
# FUNÇÃO PARA CARREGAR DADOS
# ==========================================================
@st.cache_data(ttl=600)
def carregar_dados():
    try:
        conn = st.connection("postgresql", type="sql")
        query = """
            SELECT d.nome, d.partido, g.data, g.valor, g.descricao, d.deputado_id
            FROM gastos g
            JOIN deputados d ON g.deputado_id = d.deputado_id
        """
        df_raw = conn.query(query)
        
        # Tratamentos essenciais
        df_raw["data"] = pd.to_datetime(df_raw["data"])
        df_raw["valor"] = pd.to_numeric(df_raw["valor"])
        df_raw["deputado_partido"] = df_raw["nome"] + " (" + df_raw["partido"] + ")"
        df_raw["mes_ano"] = df_raw["data"].dt.to_period("M").astype(str)
        return df_raw
    except Exception as e:
        st.error(f"Erro ao conectar no banco: {e}")
        st.stop()

df_base = carregar_dados()

# ==========================================================
# SIDEBAR — FILTRO DE DATA (AFETA TUDO)
# ==========================================================
st.sidebar.header("🔎 Filtros Globais")
periodos = sorted(df_base["mes_ano"].unique())

periodo_inicio = st.sidebar.selectbox("Mês/Ano inicial", periodos, index=0)
periodo_fim = st.sidebar.selectbox("Mês/Ano final", periodos, index=len(periodos) - 1)

# df_macro: Filtrado APENAS por data (Usado na primeira parte)
df_macro = df_base[
    (df_base["mes_ano"] >= periodo_inicio) & 
    (df_base["mes_ano"] <= periodo_fim)
].copy()

# ==========================================================
# SEÇÃO 1: PANORAMA GERAL DA CÂMARA (DADOS TOTAIS)
# ==========================================================
st.header("🌐 Panorama Geral da Câmara")
st.info(f"Dados consolidados de {periodo_inicio} até {periodo_fim}")

col_m1, col_m2, col_m3 = st.columns(3)
total_geral = df_macro["valor"].sum()
qtd_deps = df_macro["nome"].nunique()
media_nacional = total_geral / qtd_deps if qtd_deps > 0 else 0

col_m1.metric("Gasto Total da Câmara", f"R$ {total_geral:,.2f}")
col_m2.metric("Deputados com Gastos", f"{qtd_deps}")
col_m3.metric("Média por Parlamentar", f"R$ {media_nacional:,.2f}")

# --- Gastos por Partido ---
st.subheader("🏆 Gastos por Partido")
ranking_partido = df_macro.groupby("partido").agg(
    total_gasto=("valor", "sum"),
    qtd_deputados=("nome", "nunique")
).reset_index()

ranking_partido["media_por_deputado"] = ranking_partido["total_gasto"] / ranking_partido["qtd_deputados"]
ranking_partido = ranking_partido.sort_values("total_gasto", ascending=False)

fig_partido = px.bar(
    ranking_partido, x="partido", y="total_gasto",
    title="Total de Gastos por Partido",
    hover_data=["qtd_deputados", "media_por_deputado"]
)
st.plotly_chart(fig_partido, use_container_width=True)

fig_media_partido = px.bar(
    ranking_partido.sort_values("media_por_deputado", ascending=False),
    x="partido", y="media_por_deputado",
    title="Média de Gasto por Deputado em Cada Partido",
    color_discrete_sequence=['#FFA500']
)
fig_media_partido.add_hline(y=media_nacional, line_dash="dash", line_color="red", annotation_text="Média Nacional")
st.plotly_chart(fig_media_partido, use_container_width=True)

# --- Top 3 Deputados (Geral) ---
st.subheader("🥇 Top 3 Deputados que Mais Gastaram")
top_3_geral = df_macro.groupby(["nome", "partido"])["valor"].sum().sort_values(ascending=False).head(3).reset_index()
medalhas = ["🥇", "🥈", "🥉"]

cols_top = st.columns(3)
for i, row in top_3_geral.iterrows():
    cols_top[i].markdown(f"### {medalhas[i]} {row['nome']}")
    cols_top[i].write(f"**{row['partido']}**")
    cols_top[i].write(f"R$ {row['valor']:,.2f}")

st.divider()

# ==========================================================
# SIDEBAR — FILTROS ESPECÍFICOS (AFETAM ANÁLISE INDIVIDUAL)
# ==========================================================
st.sidebar.header("👤 Análise Individual")

partidos_disp = sorted(df_macro["partido"].unique())
partido_sel = st.sidebar.multiselect("Filtrar por Partido", partidos_disp, default=partidos_disp)

df_filtrado_partido = df_macro[df_macro["partido"].isin(partido_sel)]

deputados_disp = sorted(df_filtrado_partido["deputado_partido"].unique())
deputados_sel = st.sidebar.multiselect("Selecione até 5 deputados", deputados_disp, max_selections=5)

if not deputados_sel:
    st.warning("Selecione deputados na barra lateral para ver a análise individual detalhada.")

df_individual = df_filtrado_partido[df_filtrado_partido["deputado_partido"].isin(deputados_sel)]

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
# SEÇÃO 2: ANÁLISE DOS DEPUTADOS SELECIONADOS
# ==========================================================
st.header("📊 Análise dos Deputados Selecionados")

# Mapa de cores fixo
todas_descricoes = sorted(df_base["descricao"].unique())
cores = px.colors.qualitative.Alphabet
mapa_cores = {desc: cores[i % len(cores)] for i, desc in enumerate(todas_descricoes)}
mapa_cores["Outros"] = "#808080"

# Comparativo de Barras
comp_ind = df_individual.groupby("deputado_partido")["valor"].sum().reset_index()
st.plotly_chart(px.bar(comp_ind, x="deputado_partido", y="valor", title="Comparativo Direto"), use_container_width=True)

# Pizza charts com Expander
for dep in deputados_sel:
    with st.expander(f"🔍 Detalhes: {dep}"):
        df_dep = df_individual[df_individual["deputado_partido"] == dep]
        gasto_tipo = df_dep.groupby("descricao")["valor"].sum().reset_index()
        
        # Agrupar 'Outros' (< 2%)
        total_dep = gasto_tipo["valor"].sum()
        maiores = gasto_tipo[gasto_tipo["valor"]/total_dep >= 0.02].copy()
        outros_val = gasto_tipo[gasto_tipo["valor"]/total_dep < 0.02]["valor"].sum()
        
        if outros_val > 0:
            maiores = pd.concat([maiores, pd.DataFrame([{"descricao": "Outros", "valor": outros_val}])], ignore_index=True)
        
        fig_pie = px.pie(maiores, names="descricao", values="valor", title=f"Distribuição: {dep}",
                         color="descricao", color_discrete_map=mapa_cores)
        fig_pie.update_layout(legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig_pie, use_container_width=True)

# Evolução Mensal
st.subheader("📈 Evolução Mensal")
mensal = df_individual.groupby([df_individual["data"].dt.to_period("M").astype(str), "deputado_partido"])["valor"].sum().reset_index()
mensal.columns = ["mes", "deputado", "valor"]
st.plotly_chart(px.line(mensal, x="mes", y="valor", color="deputado", markers=True), use_container_width=True)

# Alertas de Anomalias
# ⚠️ GASTOS MUITO ACIMA DA MÉDIA (CORRIGIDO)
st.subheader("⚠️ Alertas: Gastos Fora do Padrão")

# O segredo está aqui: média por NOTA FISCAL (cada linha do banco), não por deputado
media_por_nota = df_macro["valor"].mean() 
limite_nota = media_por_nota * 10  # Exemplo: Notas 10x maiores que a média comum

col_a1, col_a2 = st.columns(2)
col_a1.metric("Média por Nota (Câmara)", f"R$ {media_por_nota:,.2f}")
col_a2.metric("Limite de Alerta (10x)", f"R$ {limite_nota:,.2f}")

# Filtra apenas as notas dos deputados SELECIONADOS que estouram esse limite
acima_media = df_individual[df_individual["valor"] > limite_nota]

if not acima_media.empty:
    st.warning(f"🚨 Detectamos {len(acima_media)} notas com valores atípicos entre os selecionados.")
    st.dataframe(
        acima_media[["data", "nome", "valor", "descricao"]].sort_values("valor", ascending=False),
        use_container_width=True,
        hide_index=True,
        column_config={"valor": st.column_config.NumberColumn("Valor", format="R$ %.2f")}
    )
else:
    st.success("✅ Nenhuma nota individual com valor extremo encontrada para estes deputados.")

# Lista Final
st.subheader("📄 Lista Completa de Gastos (Selecionados)")
st.dataframe(
    df_individual[["data", "nome", "partido", "valor", "descricao"]].sort_values("data", ascending=False),
    use_container_width=True,
    column_config={"valor": st.column_config.NumberColumn("Valor", format="R$ %.2f")}
)
