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

# ==========================================================
# CARREGAMENTO DE DADOS (VERSÃO LIMPA)
# ==========================================================

@st.cache_data(ttl=600)
def carregar_dados():
    # O Streamlit busca a 'url' nos Secrets [connections.postgresql] automaticamente
    # Ele NÃO precisa de int() ou os.getenv aqui
    conn = st.connection("postgresql", type="sql")
    
    query = """
        SELECT d.nome, d.partido, g.data, g.valor, g.descricao
        FROM gastos g
        JOIN deputados d ON g.deputado_id = d.deputado_id
    """
    return conn.query(query)

# --- EXECUÇÃO SEGURA ---
try:
    df = carregar_dados()
    # Cria um mapeamento de cores fixo para todas as descrições da base
    todas_descricoes = sorted(df["descricao"].unique())
    cores_disponiveis = px.colors.qualitative.Alphabet # Paleta com 26 cores diferentes

    # Dicionário que liga cada tipo de gasto a uma cor específica
    mapa_cores_fixo = {desc: cores_disponiveis[i % len(cores_disponiveis)] for i, desc in enumerate(todas_descricoes)}
    mapa_cores_fixo["Outros"] = "#808080" # Força o cinza para o grupo "Outros"

    # Só faz o tratamento se o df foi criado com sucesso
    if df is not None and not df.empty:
        df["data"] = pd.to_datetime(df["data"])
        df["valor"] = pd.to_numeric(df["valor"])
        df["deputado_partido"] = df["nome"] + " (" + df["partido"] + ")"
    
        #LINHA PARA SALVAR O GRÁFICO DE EVOLUÇÃO:
        df["mes"] = df["data"].dt.to_period("M").astype(str)
    
        # (Pode manter a 'mes_ano' também se os filtros usarem ela)
        df["mes_ano"] = df["mes"] 

    else:
        st.warning("O banco de dados parece estar vazio.")
        st.stop()

except Exception as e:
    st.error(f"Erro de conexão: {e}")
    st.stop()

# --- AQUI COMEÇA O SEU CÓDIGO ORIGINAL (SIDEBAR, FILTROS, ETC.) ---
# A partir daqui seu código já vai encontrar a coluna 'mes_ano' pronta.


except Exception as e:
    st.error(f"Erro de conexão: {e}")
    st.info("Verifique se a 'url' nos Secrets do Streamlit está correta.")
    st.stop() # Evita o NameError nas linhas abaixo

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
# 🏛️ GASTO TOTAL DA CÂMARA (APENAS FILTRO DE TEMPO)
# ==========================================================
st.subheader("🏛️ Gasto Total da Câmara no Período")

# Filtramos a base completa apenas pelo tempo selecionado no sidebar
df_camera_total = df[
    (df["mes_ano"] >= periodo_inicio) & 
    (df["mes_ano"] <= periodo_fim)
]

total_camera = df_camera_total["valor"].sum()
qtd_total_docs = len(df_camera_total)

col_cam1, col_cam2 = st.columns(2)

with col_cam1:
    st.metric(
        label="Total Gasto pela Câmara", 
        value=f"R$ {total_camera:,.2f}"
    )

with col_cam2:
    st.metric(
        label="Total de Notas Fiscais", 
        value=f"{qtd_total_docs:,}".replace(",", ".")
    )

st.caption(f"📊 Valores baseados em todos os deputados entre {periodo_inicio} e {periodo_fim}.")
st.divider()

# ==========================================================
# 🏆 PARTIDO CAMPEÃO DE GASTOS
# ==========================================================
st.subheader("🏆 Gastos por Partido")

total_partido = df.groupby("partido")["valor"].sum()
deputados_partido = df.groupby("partido")["nome"].nunique()

ranking_partido = pd.DataFrame({
    "total_gasto": total_partido,
    "qtd_deputados": deputados_partido
}).reset_index()

ranking_partido["media_por_deputado"] = (
    ranking_partido["total_gasto"] / ranking_partido["qtd_deputados"]
)

# Média Geral Nacional (calculada para a linha de referência)
media_geral_deputados = df.groupby("nome")["valor"].sum().mean()

ranking_partido = ranking_partido.sort_values("total_gasto", ascending=False)

# Gráficos em colunas (No PC lado a lado, no Celular um sob o outro)
fig_partido = px.bar(
    ranking_partido, x="partido", y="total_gasto",
    hover_data={"qtd_deputados": True, "media_por_deputado": ':.2f'},
    title="Total de Gastos por Partido"
)
st.plotly_chart(fig_partido, use_container_width=True)

fig_media = px.bar(
    ranking_partido.sort_values("media_por_deputado", ascending=False),
    x="partido", y="media_por_deputado",
    title="Média de Gasto por Deputado"
)
fig_media.add_hline(y=media_geral_deputados, line_dash="dash", line_color="red", annotation_text="Média Nacional")
st.plotly_chart(fig_media, use_container_width=True)

st.info(f"📌 Média nacional de gasto por deputado: R$ {media_geral_deputados:,.2f}")
st.divider()

# ==========================================================
# 🥇 TOP 3 DEPUTADOS (LAYOUT EM MÉTRICAS)
# ==========================================================
st.subheader("🥇 Top 3 Deputados que Mais Gastaram")

ranking_deputados = (
    df.groupby(["nome", "partido"])["valor"]
    .sum().sort_values(ascending=False).head(3).reset_index()
)

if not ranking_deputados.empty:
    m_cols = st.columns(3) # No celular, vira uma lista vertical automática
    medalhas = ["🥇", "🥈", "🥉"]
    for i, row in ranking_deputados.iterrows():
        m_cols[i].metric(label=f"{medalhas[i]} {row['nome']}", 
                         value=f"R$ {row['valor']:,.2f}", 
                         delta=row['partido'], delta_color="off")
else:
    st.info("Sem dados suficientes.")

st.divider()

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
st.subheader("🏆 Ranking de Gastos Acima da Média")

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

    # Exibição do Top 3 em colunas (melhor para celular)
    r_cols = st.columns(min(len(ranking_acima), 3))
    medalhas = ["🥇", "🥈", "🥉"]

    for i, row in ranking_acima.head(3).iterrows():
        with r_cols[i]:
            st.metric(
                label=f"{medalhas[i]} {row['nome']}", 
                value=f"{row['qtd_ocorrencias']} notas",
                delta=f"R$ {row['total_acima']:,.0f} total",
                delta_color="inverse" # Fica vermelho/alerta
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





