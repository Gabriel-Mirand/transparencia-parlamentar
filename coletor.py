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

# Carrega variáveis do .env (local) ou Secrets (GitHub)
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
    "port": int(os.getenv("DB_PORT", 6543)), # Conexão via Pooler
    "sslmode": "require"
}

MAX_WORKERS = 5
ATIVAR_AGENDAMENTO = False 

# Logging configurado para aparecer no console do GitHub Actions
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def criar_sessao():
    session = requests.Session()
    # Identificação essencial para evitar bloqueio da API
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Accept': 'application/json'
    })
    retry = Retry(
        total=5,
        backoff_factor=2, # Aumentei o tempo de espera entre tentativas
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    return session



# ==========================================================
# FUNÇÕES DE BANCO E COLETA
# ==========================================================

def obter_todos_deputados():
    session = criar_sessao()
    deputados_completos = []
    pagina = 1
    while True:
        params = {"ordem": "ASC", "ordenarPor": "nome", "itens": 100, "pagina": pagina}
        resposta = session.get(API_DEPUTADOS, params=params, timeout=30)
        
        # Verifica se a resposta foi bem sucedida
        if resposta.status_code != 200:
            logging.error(f"Erro na API: Status {resposta.status_code}")
            break
            
        # Verifica se o conteúdo não está vazio
        if not resposta.text.strip():
            logging.error("API retornou corpo vazio")
            break

        try:
            dados_json = resposta.json()
            dados = dados_json.get("dados", [])
            if not dados: break
            
            for dep in dados:
                deputados_completos.append({
                    "id": dep["id"],
                    "nome": dep["nome"],
                    "partido": dep.get("siglaPartido", "S/P"),
                    "uf": dep.get("siglaUf", "??")
                })
            pagina += 1
        except requests.exceptions.JSONDecodeError:
            logging.error(f"Erro ao decodificar JSON na página {pagina}. Conteúdo: {resposta.text[:100]}")
            break
            
    logging.info(f"Total de deputados encontrados: {len(deputados_completos)}")
    return deputados_completos

def obter_ultima_data(cursor, deputado_id):
    cursor.execute("SELECT MAX(data) FROM gastos WHERE deputado_id = %s", (deputado_id,))
    res = cursor.fetchone()
    return res[0] if res and res[0] else None

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
            str(item.get("codDocumento")) # Garante que códigos alfanuméricos entrem
        ))
    if not registros: return
    query = """
        INSERT INTO gastos (deputado_id, data, valor, descricao, cod_documento)
        VALUES (%s,%s,%s,%s,%s) ON CONFLICT (cod_documento) DO NOTHING;
    """
    execute_batch(cursor, query, registros)

def coletar_deputado(dep_dict):
    dep_id = dep_dict["id"]
    logging.info(f"Processando: {dep_dict['nome']} ({dep_dict['uf']})")
    session = criar_sessao()
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    try:
        # Garante o deputado com Nome, Partido e UF reais antes dos gastos
        cursor.execute("""
            INSERT INTO deputados (deputado_id, nome, partido, uf)
            VALUES (%s, %s, %s, %s) 
            ON CONFLICT (deputado_id) DO UPDATE SET 
                nome = EXCLUDED.nome, 
                partido = EXCLUDED.partido,
                uf = EXCLUDED.uf;
        """, (dep_id, dep_dict["nome"], dep_dict["partido"], dep_dict["uf"]))
        conn.commit()

        ultima_data = obter_ultima_data(cursor, dep_id)
        pagina = 1
        while True:
            params = {"pagina": pagina, "itens": 100, "ordem": "ASC", "ordenarPor": "dataDocumento"}
            resposta = session.get(API_DEPUTADO_DESESPESAS.format(deputado_id=dep_id), params=params, timeout=30)
            if resposta.status_code != 200: break
            dados = resposta.json().get("dados", [])
            if not dados: break

            if ultima_data:
                dados = [item for item in dados if datetime.strptime(item.get("dataDocumento"), "%Y-%m-%d").date() > ultima_data]
            
            if not dados: break
            salvar_gastos(cursor, dep_id, dados)
            conn.commit()
            pagina += 1
    except Exception as e:
        logging.error(f"Erro no deputado {dep_id}: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def coletar_varios(deputados_lista):
    logging.info("==== INÍCIO DA COLETA ====")
    # Processa em lotes (batches) para respeitar o limite de workers
    for i in range(0, len(deputados_lista), MAX_WORKERS):
        batch = deputados_lista[i:i+MAX_WORKERS]
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(coletar_deputado, dep) for dep in batch]
            for future in as_completed(futures):
                try: future.result()
                except Exception as e: logging.error(f"Erro na thread: {e}")
    logging.info("==== FIM DA COLETA ====")

# ==========================================================
# PONTO DE ENTRADA
# ==========================================================
if __name__ == "__main__":
    print("Iniciando processo de coleta...")
    lista_deputados = obter_todos_deputados()
    coletar_varios(lista_deputados)
    print("Processo concluído com sucesso!")




