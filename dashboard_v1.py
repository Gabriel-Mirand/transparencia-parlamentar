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
# 🏆 PARTIDO CAMPEÃO DE GASTOS
# ==========================================================
st.subheader("🏆 Gastos por Partido")

# Total gasto por partido
total_partido = df.groupby("partido")["valor"].sum()

# Número de deputados por partido
deputados_partido = df.groupby("partido")["nome"].nunique()

# Criar dataframe consolidado
ranking_partido = pd.DataFrame({
    "total_gasto": total_partido,
    "qtd_deputados": deputados_partido
}).reset_index()

# Calcular média por deputado
ranking_partido["media_por_deputado"] = (
    ranking_partido["total_gasto"] / ranking_partido["qtd_deputados"]
)

# ==========================================================
# 📊 MÉDIA GERAL DE GASTO POR DEPUTADO (TODOS)
# ==========================================================

media_individual = (
    df.groupby("nome")["valor"]
    .sum()
)

media_geral_deputados = media_individual.mean()

# Ordenar por total gasto
ranking_partido = ranking_partido.sort_values(
    "total_gasto",
    ascending=False
)

# Gráfico de barras (Total)
fig_partido = px.bar(
    ranking_partido,
    x="partido",
    y="total_gasto",
    hover_data={
        "qtd_deputados": True,
        "media_por_deputado": ':.2f'
    },
    title="Total de Gastos por Partido"
)

st.plotly_chart(fig_partido, use_container_width=True)

fig_media = px.bar(
    ranking_partido.sort_values("media_por_deputado", ascending=False),
    x="partido",
    y="media_por_deputado",
    title="Média de Gasto por Deputado em Cada Partido"
)

# Linha horizontal da média geral
fig_media.add_hline(
    y=media_geral_deputados,
    line_dash="dash",
    line_color="red",
    annotation_text="Média Geral Nacional",
    annotation_position="top right"
)

st.plotly_chart(fig_media, use_container_width=True)

st.info(
    f"📌 Média geral de gasto por deputado (todos os partidos): "
    f"R$ {media_geral_deputados:,.2f}"
)

st.divider()

# ==========================================================
# 🥇 TOP 3 DEPUTADOS QUE MAIS GASTARAM
# ==========================================================
st.subheader("🥇 Top 3 Deputados que Mais Gastaram")

ranking_deputados = (
    df.groupby(["nome", "partido"])["valor"]
    .sum()
    .sort_values(ascending=False)
    .head(3)
    .reset_index()
)

medalhas = ["🥇", "🥈", "🥉"]

if not ranking_deputados.empty:
    for i, row in ranking_deputados.iterrows():
        st.markdown(
            f"### {medalhas[i]} {row['nome']} ({row['partido']}) — R$ {row['valor']:,.2f}"
        )
else:
    st.info("Não há dados suficientes para gerar o ranking.")

st.divider()

# ==========================================================
# 📊 COMPARAÇÃO ENTRE DEPUTADOS
# ==========================================================
st.subheader("📊 Comparação Entre Deputados")

comparacao = (
    df_filtrado.groupby("deputado_partido")["valor"]
    .sum()
    .reset_index()
)

fig_comp = px.bar(
    comparacao,
    x="deputado_partido",
    y="valor",
    title="Total Gasto por Deputado"
)

st.plotly_chart(fig_comp, use_container_width=True)

# ----------------------------------------------------------
# Mostrar valores por escrito
# ----------------------------------------------------------
st.markdown("### 💰 Valor Total Gasto por Deputado")

for _, row in comparacao.iterrows():
    deputado = row["deputado_partido"]
    valor = row["valor"]

    st.write(f"**{deputado}** gastou **R$ {valor:,.2f}** no período selecionado.")

st.divider()

# ==========================================================
# 📊 GASTOS POR TIPO PARA CADA DEPUTADO
# ==========================================================
st.subheader("🧾 Distribuição de Gastos por Tipo (por Deputado)")

for deputado in df_filtrado["deputado_partido"].unique():

    st.markdown(f"### {deputado}")

    df_dep = df_filtrado[df_filtrado["deputado_partido"] == deputado]

    gasto_tipo = (
        df_dep.groupby("descricao")["valor"]
        .sum()
        .reset_index()
    )

    total_gastos = gasto_tipo["valor"].sum()

    # calcular percentual
    gasto_tipo["percentual"] = (gasto_tipo["valor"] / total_gastos) * 100

    # separar maiores de 2%
    maiores = gasto_tipo[gasto_tipo["percentual"] >= 2]

    # menores que 2%
    menores = gasto_tipo[gasto_tipo["percentual"] < 2]

    if not menores.empty:
        outros_valor = menores["valor"].sum()

        maiores = pd.concat([
            maiores,
            pd.DataFrame([{
                "descricao": "Outros",
                "valor": outros_valor,
                "percentual": (outros_valor / total_gastos) * 100
            }])
        ])

    fig_tipo = px.pie(
        maiores,
        names="descricao",
        values="valor",
        title=f"Distribuição de gastos — {deputado}"
    )

    st.plotly_chart(fig_tipo, use_container_width=True)

st.markdown(
    "💡 Tipos de gasto com menos de 2% do total foram agrupados como 'Outros'."
)

st.divider()

# ==========================================================
# 📈 EVOLUÇÃO MENSAL
# ==========================================================
st.subheader("📈 Evolução Mensal")

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
    title="Gastos ao longo do tempo"
)

st.plotly_chart(fig_linha, use_container_width=True)

st.divider()

# ==========================================================
# ⚠️ GASTOS MUITO ACIMA DA MÉDIA (BASE COMPLETA)
# ==========================================================
st.subheader("⚠️ Gastos Muito Acima da Média")

# 🔹 Média considerando TODOS os gastos da base
media_geral = df["valor"].mean()

# Definição de muito acima da média (5x)
limite = media_geral * 5

st.markdown(
    f"📊 Média geral considerando TODOS os gastos da base: "
    f"**R$ {media_geral:,.2f}**"
)

st.markdown(
    f"🔎 Consideramos como 'muito acima da média' valores superiores a "
    f"**R$ {limite:,.2f}** (5x a média geral)."
)

# Agora filtramos apenas dentro do que está sendo exibido
acima_media = df_filtrado[df_filtrado["valor"] > limite]

if not acima_media.empty:

    st.warning(
        f"Foram encontrados {len(acima_media)} gastos muito acima da média."
    )

    st.dataframe(
        acima_media[
            ["nome", "partido", "data", "valor", "descricao"]
        ].sort_values("valor", ascending=False)
    )

else:
    st.success("Nenhum gasto muito acima da média foi encontrado.")

st.divider()

# ==========================================================
# 🏆 RANKING DE DEPUTADOS COM MAIS GASTOS ACIMA DA MÉDIA
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

    medalhas = ["🥇", "🥈", "🥉"]

    # Mostrar Top 3 com medalhas
    for posicao, (_, row) in enumerate(ranking_acima.head(3).iterrows()):
        medalha = medalhas[posicao] if posicao < 3 else ""

        st.markdown(
            f"{medalha} **{row['nome']} ({row['partido']})**  \n"
            f"- Ocorrências acima da média: {row['qtd_ocorrencias']}  \n"
            f"- Total gasto acima da média: R$ {row['total_acima']:,.2f}"
        )

    st.markdown("---")
    st.dataframe(ranking_acima)

else:
    st.info("Nenhum deputado possui gastos acima da média para gerar ranking.")

st.divider()

# ==========================================================
# 📄 TABELA FINAL
# ==========================================================
st.subheader("📄 Lista Completa de Gastos")

# Lista apenas as colunas amigáveis para o usuário ver
colunas_visiveis = ["data", "nome", "partido", "valor", "descricao"]

st.dataframe(
    df_filtrado[colunas_visiveis].sort_values("data", ascending=False),
    use_container_width=True,
    hide_index=True # Remove a coluna de números à esquerda, economizando espaço no celular
)











