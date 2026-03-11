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
import os
from dotenv import load_dotenv

load_dotenv()

# ==========================================================
# CONFIGURAÇÕES
# ==========================================================
API_DEPUTADOS = "https://dadosabertos.camara.leg.br"
API_DEPUTADO_DESESPESAS = "https://dadosabertos.camara.leg.br/{deputado_id}/despesas"

DB_CONFIG = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT", 6543)),
    "sslmode": "require"
}

MAX_WORKERS = 5
ATIVAR_AGENDAMENTO = False 

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def criar_sessao():
    session = requests.Session()
    retry = Retry(total=5, backoff_factor=1, status_forcelist=[500,502,503,504], allowed_methods=["GET"])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    return session

# ==========================================================
# FUNÇÕES DE BANCO
# ==========================================================
def obter_todos_deputados():
    session = criar_sessao()
    deputados_ids = []
    pagina = 1
    while True:
        params = {"ordem": "ASC", "ordenarPor": "nome", "itens": 100, "pagina": pagina}
        resposta = session.get(API_DEPUTADOS, params=params, timeout=30)
        if resposta.status_code != 200: break
        dados = resposta.json().get("dados", [])
        if not dados: break
        deputados_ids.extend([dep["id"] for dep in dados])
        pagina += 1
    return deputados_ids

def obter_ultima_data(cursor, deputado_id):
    cursor.execute("SELECT MAX(data) FROM gastos WHERE deputado_id = %s", (deputado_id,))
    res = cursor.fetchone()
    return res[0] if res else None

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
            str(item.get("codDocumento")) # Convertido para string para evitar erro alfanumérico
        ))
    if not registros: return
    query = """
        INSERT INTO gastos (deputado_id, data, valor, descricao, cod_documento)
        VALUES (%s,%s,%s,%s,%s) ON CONFLICT (cod_documento) DO NOTHING;
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
    
    try:
        # Garante que o deputado existe para respeitar a Foreign Key
        cursor.execute("""
            INSERT INTO deputados (deputado_id, nome, partido)
            VALUES (%s, %s, %s) ON CONFLICT (deputado_id) DO NOTHING;
        """, (deputado_id, "Nome Indisponível", "S/P"))
        conn.commit()

        ultima_data = obter_ultima_data(cursor, deputado_id)
        pagina = 1

        while True:
            params = {"pagina": pagina, "itens": 100, "ordem": "ASC", "ordenarPor": "dataDocumento"}
            resposta = session.get(API_DEPUTADO_DESESPESAS.format(deputado_id=deputado_id), params=params, timeout=30)
            if resposta.status_code != 200: break
            dados = resposta.json().get("dados", [])
            if not dados: break

            if ultima_data:
                dados = [item for item in dados if datetime.strptime(item.get("dataDocumento"), "%Y-%m-%d").date() > ultima_data]
            
            if not dados: break
            salvar_gastos(cursor, deputado_id, dados)
            conn.commit()
            pagina += 1
    except Exception as e:
        logging.error(f"Erro deputado {deputado_id}: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

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
# PONTO DE ENTRADA
# ==========================================================
if __name__ == "__main__":
    print("Obtendo lista completa de deputados...")
    todos_deputados = obter_todos_deputados()
    print("Executando coleta inicial...")
    coletar_varios(todos_deputados)
    print("Sucesso: Coleta finalizada.")

