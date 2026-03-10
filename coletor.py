# ==========================================================
# IMPORTS
# ==========================================================
import requests
import logging
import psycopg2
from psycopg2.extras import execute_batch
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import schedule
import time

# ==========================================================
# CONFIGURAÇÕES
# ==========================================================

import os
from dotenv import load_dotenv

# Carrega variáveis do .env
load_dotenv()

API_DEPUTADOS = "https://dadosabertos.camara.leg.br/api/v2/deputados"
API_DEPUTADO_DESESPESAS = "https://dadosabertos.camara.leg.br/api/v2/deputados/{deputado_id}/despesas"

# Configuração do banco usando variáveis do .env
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "sslmode": "require"
}

MAX_WORKERS = 5
HORARIO_EXECUCAO = "02:00"  # horário diário do job

# ==========================================================
# FLAG DE AGENDAMENTO DIÁRIO - False -> PARA RODAR NO GITHUB OU APENAS UM VEZ LOCALMENTE - True -> PARA RODAR LOCALMENTE (WHILE)
# ==========================================================
ATIVAR_AGENDAMENTO = False  # True = roda diariamente / False = não roda

# ==========================================================
# LOGGING
# ==========================================================
logging.basicConfig(
    filename="coletor.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ==========================================================
# SESSÃO HTTP COM RETRY
# ==========================================================
def criar_sessao():
    session = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[500,502,503,504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    return session

# ==========================================================
# PEGAR TODOS OS DEPUTADOS
# ==========================================================
def obter_todos_deputados():
    session = criar_sessao()
    deputados_ids = []
    pagina = 1

    while True:
        params = {"ordem": "ASC", "ordenarPor": "nome", "itens": 100, "pagina": pagina}
        resposta = session.get(API_DEPUTADOS, params=params, timeout=30)
        if resposta.status_code != 200:
            logging.error(f"Erro ao obter deputados: {resposta.status_code}")
            break

        dados = resposta.json().get("dados", [])
        if not dados:
            break

        deputados_ids.extend([dep["id"] for dep in dados])
        pagina += 1

    logging.info(f"Total de deputados encontrados: {len(deputados_ids)}")
    return deputados_ids

# ==========================================================
# FUNÇÕES DE BANCO
# ==========================================================
def obter_ultima_data(cursor, deputado_id):
    cursor.execute("SELECT MAX(data) FROM gastos WHERE deputado_id = %s", (deputado_id,))
    return cursor.fetchone()[0]

def salvar_gastos(cursor, deputado_id, dados):
    registros = []
    for item in dados:
        data_doc = item.get("dataDocumento")
        if not data_doc: continue
        registros.append((
            deputado_id,
            data_doc,
            item.get("valorDocumento"),
            item.get("tipoDespesa"),
            item.get("codDocumento")
        ))
    if not registros: return
    query = """
        INSERT INTO gastos (deputado_id, data, valor, descricao, cod_documento)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (cod_documento) DO NOTHING;
    """
    execute_batch(cursor, query, registros)

# ==========================================================
# COLETA DE DESPESAS DE UM DEPUTADO
# ==========================================================
def coletar_deputado(deputado_id):
    logging.info(f"Iniciando coleta deputado {deputado_id}")
    session = criar_sessao()
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    pagina = 1

    try:
        ultima_data = obter_ultima_data(cursor, deputado_id)

        while True:
            params = {"pagina": pagina, "itens": 100, "ordem": "ASC", "ordenarPor": "dataDocumento"}
            resposta = session.get(API_DEPUTADO_DESESPESAS.format(deputado_id=deputado_id), params=params, timeout=30)
            if resposta.status_code != 200:
                logging.error(f"Erro HTTP {resposta.status_code} deputado {deputado_id}")
                break

            dados = resposta.json().get("dados", [])
            if not dados:
                break

            # filtrar apenas gastos novos
            if ultima_data:
                dados = [item for item in dados if datetime.strptime(item.get("dataDocumento"), "%Y-%m-%d").date() > ultima_data]
                if not dados:
                    break

            salvar_gastos(cursor, deputado_id, dados)
            conn.commit()
            pagina += 1

        logging.info(f"Finalizado deputado {deputado_id}")

    except Exception as e:
        logging.error(f"Erro deputado {deputado_id}: {e}")
        conn.rollback()

    finally:
        cursor.close()
        conn.close()

# ==========================================================
# COLETA DE VÁRIOS DEPUTADOS EM PARALELO
# ==========================================================
def coletar_varios(deputados_ids):
    logging.info("==== INÍCIO DA COLETA ====")
    for i in range(0, len(deputados_ids), MAX_WORKERS):
        batch = deputados_ids[i:i+MAX_WORKERS]
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(coletar_deputado, dep_id) for dep_id in batch]
            for future in as_completed(futures):
                try: future.result()
                except Exception as e: logging.error(f"Erro thread: {e}")
    logging.info("==== FIM DA COLETA ====")

# ==========================================================
# AGENDAMENTO DIÁRIO - UTILIZE APENAS QUANDO ESTIVER RODANDO LOCALMENTE - NÃO UTILIZAR NO GITHUB
# O AGENDAMENTO DIÁRIO DEVE SER = False VER LINHA 41
# ==========================================================
def iniciar_agendamento(deputados_ids):
    schedule.every().day.at(HORARIO_EXECUCAO).do(lambda: coletar_varios(deputados_ids))
    print(f"Agendado para executar diariamente às {HORARIO_EXECUCAO}")
    while True:
        schedule.run_pending()
        time.sleep(60)

# ==========================================================
# PONTO DE ENTRADA
# ==========================================================
if __name__ == "__main__":
    print("Obtendo lista completa de deputados...")
    todos_deputados = obter_todos_deputados()
    
    print("Executando coleta inicial...")
    coletar_varios(todos_deputados)
    
    if ATIVAR_AGENDAMENTO:
        iniciar_agendamento(todos_deputados)
    else:

        print("Agendamento diário está DESATIVADO. Apenas coleta inicial executada.")
