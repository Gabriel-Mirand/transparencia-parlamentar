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
    "port": int(os.getenv("DB_PORT", 6543)),
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
# PEGAR TODOS OS DEPUTADOS (ATUALIZADO PARA PEGAR NOME, PARTIDO E UF)
# ==========================================================
def obter_todos_deputados():
    session = criar_sessao()
    deputados_completos = []
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

        for dep in dados:
            deputados_completos.append({
                "id": dep["id"],
                "nome": dep["nome"],
                "partido": dep.get("siglaPartido", "S/P"),
                "uf": dep.get("siglaUf", "??")
            })
        pagina += 1

    logging.info(f"Total de deputados encontrados: {len(deputados_completos)}")
    return deputados_completos

# ==========================================================
# COLETA DE DESPESAS DE UM DEPUTADO (ATUALIZADA)
# ==========================================================
def coletar_deputado(dep_dict):
    deputado_id = dep_dict["id"]
    logging.info(f"Iniciando coleta deputado {deputado_id} - {dep_dict['nome']}")
    session = criar_sessao()
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    pagina = 1

    try:
        # Insere/Atualiza os dados reais do deputado incluindo UF
        cursor.execute("""
            INSERT INTO deputados (deputado_id, nome, partido, uf)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (deputado_id) DO UPDATE SET 
                nome = EXCLUDED.nome, 
                partido = EXCLUDED.partido,
                uf = EXCLUDED.uf;
        """, (deputado_id, dep_dict["nome"], dep_dict["partido"], dep_dict["uf"]))
        conn.commit()
        
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

            if dados and ultima_data is not None:
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
# COLETA DE VÁRIOS DEPUTADOS (ATUALIZADA)
# ==========================================================
def coletar_varios(deputados_lista):
    logging.info("==== INÍCIO DA COLETA ====")
    for i in range(0, len(deputados_lista), MAX_WORKERS):
        batch = deputados_lista[i:i+MAX_WORKERS]
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Agora passamos o dicionário completo 'dep' para a função
            futures = [executor.submit(coletar_deputado, dep) for dep in batch]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logging.error(f"Erro thread: {e}")
    logging.info("==== FIM DA COLETA ====")

# ==========================================================
# PONTO DE ENTRADA (CORRIGIDO)
# ==========================================================
if __name__ == "__main__":
    print("Obtendo lista completa de deputados...")
    todos_deputados = obter_todos_deputados()
    
    print("Executando coleta inicial...")
    coletar_varios(todos_deputados)
    
    if ATIVAR_AGENDAMENTO:
        iniciar_agendamento(todos_deputados)
    else:
        print("Coleta finalizada. Script encerrado.")
