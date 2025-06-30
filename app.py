# app.py - Backend Flask para proxy da Evolution API e gerenciamento de Leads

import os
import requests
import json
import sqlite3
import urllib.parse
from flask import Flask, request, jsonify, g
from dotenv import load_dotenv
from flask_cors import CORS
import time
import traceback
import random # Para ajudar a gerar nomes aleatórios/sugestões

# --- Configuração do Flask ---
app = Flask(__name__)
CORS(app)

# --- Carregar Variáveis de Ambiente ---
load_dotenv()

# --- Configurações da Evolution API ---
EVOLUTION_API_URL = os.getenv('EVOLUTION_API_URL')
GLOBAL_API_KEY = os.getenv('GLOBAL_API_KEY')

if not EVOLUTION_API_URL or not GLOBAL_API_KEY:
    print("===============================================")
    print("!! ERRO DE CONFIGURAÇÃO:                        !!")
    print("!! EVOLUTION_API_URL ou GLOBAL_API_KEY não     !!")
    print("!! configurada nas variáveis de ambiente.      !!")
    print("!! Crie ou edite o arquivo .env na raiz.       !!")
    print("===============================================")
    # Em produção, considere parar o app aqui.
    # import sys
    # sys.exit("Configuração de API faltando!")
    # Para desenvolvimento local, apenas avisamos.

# Remove barra final da URL da Evolution API se existir
if EVOLUTION_API_URL and EVOLUTION_API_URL.endswith('/'):
    EVOLUTION_API_URL = EVOLUTION_API_URL[:-1]


# --- Configuração do Banco de Dados (SQLite) ---
DATABASE_FILE = os.getenv('DATABASE_FILE', 'database.db')
DATABASE_PATH = os.path.join(app.root_path, DATABASE_FILE) # Coloca o DB na pasta raiz do app

# Função para conectar ao banco de dados
def get_db():
    """Conecta ao banco de dados e configura o cursor."""
    db = getattr(g, '_database', None) # Usa o objeto 'g' do Flask para reutilizar a conexão na mesma requisição
    if db is None:
        db = g._database = sqlite3.connect(DATABASE_PATH)
        # Configura para retornar linhas como dicionários (facilita o acesso por nome da coluna)
        db.row_factory = sqlite3.Row
    return db

# Fechar a conexão com o banco de dados ao final da requisição
@app.teardown_appcontext
def close_db(error):
    """Fecha a conexão com o banco de dados ao final do contexto da requisição."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# Função para inicializar o banco de dados (criar tabelas)
def init_db():
    """Cria as tabelas do banco de dados se não existirem."""
    try:
        with app.app_context():
            db = get_db()
            # Verifica se o arquivo schema.sql existe
            schema_path = os.path.join(app.root_path, 'schema.sql')
            if not os.path.exists(schema_path):
                 print(f"ERRO: Arquivo schema.sql não encontrado em {schema_path}")
                 return False # Falha na inicialização
            with app.open_resource('schema.sql', mode='r') as f: # Lê o script SQL de um arquivo
                db.cursor().executescript(f.read())
            db.commit()
        print("Banco de dados inicializado (tabelas criadas ou já existentes).")
        return True
    except Exception as e:
        print(f"ERRO ao inicializar o banco de dados: {e}")
        traceback.print_exc()
        return False # Falha na inicialização


# Helper para inicializar o banco na primeira execução (se o arquivo não existir)
@app.before_request
def check_db_exists_and_init():
    # Esta checagem roda ANTES de CADA requisição.
    # É ineficiente em produção, mas simples para desenvolvimento inicial.
    # Em produção, use um script de deploy ou um comando separado para rodar init_db() uma vez.
    if not os.path.exists(DATABASE_PATH):
        print(f"Arquivo de banco de dados '{DATABASE_FILE}' não encontrado. Tentando inicializar...")
        if not init_db():
             # Se falhou a inicialização, podemos retornar um erro 500 imediatamente
             # Note: Retornar diretamente de before_request interrompe a requisição
             # Para este caso específico, talvez seja melhor deixar a requisição seguir
             # e o erro de DB ocorrerá na primeira tentativa de acesso ao DB.
             pass # Apenas loga o erro e continua, o erro real ocorrerá em get_db/save_instance_status


# --- Funções Auxiliares para Interagir com a Evolution API ---

def make_evolution_request(method, endpoint, instance_name=None, json_data=None):
    """Faz uma requisição genérica para a Evolution API."""
    if not EVOLUTION_API_URL or not GLOBAL_API_KEY:
         # Retorna um erro interno se a API Evolution não está configurada no backend
         return {"error": "Configuração da Evolution API incompleta no backend."}, 500

    url = f"{EVOLUTION_API_URL}{endpoint}"
    if instance_name:
        # Assegura que o instance_name é URL-safe ao usá-lo no caminho da URL
        instance_name_encoded = urllib.parse.quote(str(instance_name)) # Garante que é string e encoda
        # Usa regex simples para substituir placeholders como <instance_name> ou {instance_name}
        url = url.replace('<instance_name>', instance_name_encoded).replace('{instance_name}', instance_name_encoded)


    headers = {
        "apikey": GLOBAL_API_KEY,
        "Content-Type": "application/json"
    }

    try:
        print(f"Proxy -> Evolution: {method} {url}")
        if json_data:
             # Remove a API Key do log se estiver presente no payload (não deveria, mas por precaução)
             log_payload = json_data.copy() if isinstance(json_data, dict) else json_data
             if isinstance(log_payload, dict) and 'apikey' in log_payload:
                  log_payload['apikey'] = '***MASKED***'
             # Limita o tamanho do payload no log para não poluir
             payload_str = json.dumps(log_payload)
             print(f"  Payload: {payload_str[:500]}{'...' if len(payload_str) > 500 else ''}")


        response = requests.request(method, url, headers=headers, json=json_data, timeout=60) # Aumenta timeout para 60s
        response.raise_for_status() # Lança um HTTPError para códigos de status ruins (4xx ou 5xx)

        # Tenta retornar JSON. Se falhar (resposta não JSON), retorna texto e status.
        try:
            response_json = response.json()
            # Limita o tamanho do body no log para não poluir
            body_str = json.dumps(response_json)
            print(f"Proxy <- Evolution: Status: {response.status_code}, Body: {body_str[:500]}{'...' if len(body_str) > 500 else ''}")
            return response_json, response.status_code
        except requests.exceptions.JSONDecodeError:
            print(f"Proxy <- Evolution: Resposta não é JSON. Status: {response.status_code}, Texto: {response.text[:200]}...") # Limita texto do log
            return {"message": response.text, "status_code_evolution": response.status_code}, response.status_code

    except requests.exceptions.Timeout:
        print(f"Proxy <- Evolution: Timeout na requisição para {url}")
        return {"error": "Timeout ao comunicar com a Evolution API."}, 504 # Gateway Timeout
    except requests.exceptions.ConnectionError as e:
        print(f"Proxy <- Evolution: Erro de conexão com a Evolution API: {e}")
        return {"error": f"Erro de conexão com a Evolution API: {e}"}, 503 # Service Unavailable
    except requests.exceptions.HTTPError as e:
        status_code_evo = e.response.status_code
        error_text_evo = e.response.text
        print(f"Proxy <- Evolution: Erro HTTP ({status_code_evo}): {error_text_evo}")
        # Tenta parsear o erro JSON da Evolution API, se existir
        try:
            error_detail = e.response.json()
        except requests.exceptions.JSONDecodeError:
            error_detail = {"message": error_text_evo}

        # Adiciona o nome da instância ao erro retornado, se disponível
        error_detail['instanceName'] = instance_name

        return {"error": f"Erro da Evolution API ({status_code_evo}): {error_detail.get('message', error_text_evo)}",
                "evolution_status_code": status_code_evo,
                "detail": error_detail}, status_code_evo
    except Exception as e:
        print(f"Proxy <- Internal Server Error: {e}")
        traceback.print_exc() # Imprime o stacktrace completo para debugging
        return {"error": f"Erro interno do backend: {e}"}, 500


# --- Funções de Banco de Dados (SQLite) ---

def save_instance_status(instance_name, status, owner, lead_id=None):
    """Salva ou atualiza o status e owner de uma instância no banco de dados."""
    db = get_db()
    try:
        # Se lead_id foi fornecido, incluir na atualização
        if lead_id:
            db.execute("""
                INSERT OR REPLACE INTO instances (instance_name, status, evolution_owner, lead_id, last_updated, created_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, COALESCE((SELECT created_at FROM instances WHERE instance_name = ?), CURRENT_TIMESTAMP))
            """, (instance_name, status, owner, lead_id, instance_name))
        else:
            db.execute("""
                INSERT OR REPLACE INTO instances (instance_name, status, evolution_owner, last_updated, created_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, COALESCE((SELECT created_at FROM instances WHERE instance_name = ?), CURRENT_TIMESTAMP))
            """, (instance_name, status, owner, instance_name))
        db.commit()
        print(f"BD: Status para instância '{instance_name}' salvo como '{status}' (Owner: {owner}, Lead ID: {lead_id}).")
    except Exception as e:
        print(f"ERRO BD: Falha ao salvar status para instância '{instance_name}': {e}")
        traceback.print_exc()


def get_instance_from_db(instance_name):
    """Busca as informações de uma instância no banco de dados."""
    db = get_db()
    try:
        cursor = db.execute("SELECT * FROM instances WHERE instance_name = ?", (instance_name,))
        row = cursor.fetchone()
        return row # Retorna um dicionário (Row) ou None
    except Exception as e:
        print(f"ERRO BD: Falha ao buscar instância '{instance_name}': {e}")
        traceback.print_exc()
        return None # Retorna None em caso de erro no banco

# --- Funções para Sugestão de Nomes ---

def get_existing_instance_names():
    """Busca a lista de nomes de instâncias existentes na Evolution API."""
    # Usa o endpoint fetchInstances para obter a lista completa
    fetch_endpoint = "/instance/fetchInstances"
    response_data, status_code = make_evolution_request("GET", fetch_endpoint)

    if status_code >= 200 and status_code < 300 and isinstance(response_data, list):
        # Extrai os nomes dos diferentes campos possíveis (name, instanceName)
        existing_names = [inst.get('name') or inst.get('instanceName') for inst in response_data if inst.get('name') or inst.get('instanceName')]
        print(f"Proxy <- Backend: Encontrados {len(existing_names)} nomes de instâncias existentes.")
        return existing_names
    else:
        print(f"Proxy <- Backend: Falha ao obter lista de instâncias para sugerir nomes ({status_code}).")
        return [] # Retorna lista vazia em caso de erro ou resposta inesperada

def generate_name_suggestions(base_name, existing_names, num_suggestions=5):
    """Gera sugestões de nomes de instância baseadas em um nome e nomes existentes."""
    suggestions = []
    base = base_name.lower().replace(' ', '-') # Remove espaços e deixa minúsculo
    attempt = 1

    while len(suggestions) < num_suggestions and attempt < 100: # Limita tentativas para evitar loop infinito
        suggested_name = f"{base}-{attempt}"
        if suggested_name not in existing_names:
            suggestions.append(suggested_name)
        attempt += 1

    # Adiciona algumas sugestões com números aleatórios no final
    while len(suggestions) < num_suggestions:
         random_suffix = random.randint(100, 999)
         suggested_name = f"{base}-{random_suffix}"
         if suggested_name not in existing_names and suggested_name not in suggestions:
              suggestions.append(suggested_name)
         # Sai do loop se não conseguir gerar nomes únicos após muitas tentativas
         if len(suggestions) >= num_suggestions or attempt > 200: break
         attempt += 1


    print(f"Proxy <- Backend: Sugerindo nomes para '{base_name}': {suggestions}")
    return suggestions


# --- Endpoints para o Frontend do Lead (`conexao_lead.html`) ---

@app.route('/api/lead/conectar', methods=['POST'])
def conectar_instancia():
    """
    Endpoint para criar/verificar uma instância e obter QR Code/Status.
    Recebe: {"instanceName": "nome-da-instancia"}
    Retorna: QR Code data, Status ('qrcode', 'connected', 'connecting', etc.), Sugestões de nome em caso de conflito.
    """
    data = request.json
    instance_name = data.get('instanceName')
    lead_id = request.headers.get('X-Lead-Id')

    if not instance_name:
        print("Proxy <- Backend: Nome da instância ausente na requisição /conectar.")
        return jsonify({"error": "Nome da instância é obrigatório."}), 400

    print(f"Proxy -> Backend: Recebida requisição /conectar para instância: '{instance_name}' (Lead ID: {lead_id})")

    # --- Verificar limite de instâncias se Lead ID fornecido ---
    if lead_id:
        db = get_db()
        try:
            # Buscar plano do lead
            cursor = db.execute('''
                SELECT p.max_instances 
                FROM leads l
                LEFT JOIN plans p ON l.plan_id = p.id
                WHERE l.id = ?
            ''', (lead_id,))
            
            result = cursor.fetchone()
            max_instances = result['max_instances'] if result and result['max_instances'] else 1
            
            # Contar instâncias atuais do lead
            count_cursor = db.execute('SELECT COUNT(*) as count FROM instances WHERE lead_id = ?', (lead_id,))
            current_count = count_cursor.fetchone()['count']
            
            # Verificar se já existe uma instância com este nome para este lead
            existing_cursor = db.execute('SELECT * FROM instances WHERE instance_name = ? AND lead_id = ?', 
                                       (instance_name, lead_id))
            existing_instance = existing_cursor.fetchone()
            
            if not existing_instance and current_count >= max_instances:
                print(f"Proxy <- Backend: Lead {lead_id} atingiu limite de {max_instances} instâncias")
                return jsonify({
                    'error': f'Limite de {max_instances} instâncias atingido para seu plano',
                    'limit_reached': True
                }), 403
        except Exception as e:
            print(f"Erro ao verificar limite de instâncias: {e}")
            # Continua mesmo com erro na verificação de limite

    # --- Lógica Central de Conexão/QR ---

    # 1. Tenta criar a instância (se já existir, a API Evolution retorna 409 ou 403 Forbidden)
    create_endpoint = "/instance/create"
    create_payload = {
        "instanceName": instance_name,
        "qrcode": True, # Sempre pede QR Code inicialmente
        "integration": "WHATSAPP-BAILEYS" # Ou a integração que você usa
    }

    response_data, status_code = make_evolution_request("POST", create_endpoint, json_data=create_payload)

    # Verifica se o erro é de nome já em uso (409 Conflict ou 403 Forbidden com mensagem específica)
    is_name_in_use_error = False
    if status_code in [409, 403]:
        try:
            # Tenta encontrar a mensagem específica de nome em uso na resposta
            message_detail = response_data.get('detail', {}).get('message', '')
            # A mensagem pode ser uma string ou uma lista
            if isinstance(message_detail, list):
                message_detail = " ".join(message_detail)

            # Verifica se a mensagem contém "already in use"
            if "already in use" in message_detail.lower():
                 is_name_in_use_error = True
                 print(f"Proxy <- Backend: Detectado erro de nome em uso para '{instance_name}'.")
            else:
                 print(f"Proxy <- Backend: Erro {status_code} não é de nome em uso para '{instance_name}'. Mensagem: '{message_detail}'")
        except Exception as e:
            print(f"Proxy <- Backend: Erro ao parsear resposta para verificar nome em uso: {e}. Status {status_code}.")
            # Assume que não é um erro de nome em uso se não conseguir parsear

    if is_name_in_use_error:
        # --- Regra 1: Nome em Uso ---
        print(f"Proxy -> Backend: Nome '{instance_name}' em uso. Buscando sugestões...")
        existing_names = get_existing_instance_names()
        suggestions = generate_name_suggestions(instance_name, existing_names)

        # Retorna um status 409 (Conflict) para o frontend, com detalhes do erro e sugestões
        return jsonify({
            "status": "name_in_use", # Status customizado para o frontend entender
            "error": f"O nome de conexão '{instance_name}' já está em uso na Evolution API.",
            "evolution_status_code": status_code,
            "suggestions": suggestions,
            "detail": response_data # Inclui a resposta original da API para debug
        }), 409 # Usa status HTTP 409 Conflict


    elif status_code >= 200 and status_code < 300:
        # Instância criada com sucesso (2xx).
        print(f"Proxy <- Backend: Instância '{instance_name}' criada com sucesso ({status_code}). Procedendo para obter QR ou Status.")

        # Se temos o lead_id, salvar a instância no banco como pertencente a este lead
        if lead_id:
            db = get_db()
            try:
                # Verificar se já existe registro para esta instância e lead
                existing = db.execute('SELECT * FROM instances WHERE instance_name = ? AND lead_id = ?', 
                                    (instance_name, lead_id)).fetchone()
                
                if not existing:
                    # Criar nova instância no banco
                    db.execute('''
                        INSERT INTO instances (lead_id, instance_name, status) 
                        VALUES (?, ?, 'connecting')
                    ''', (lead_id, instance_name))
                    db.commit()
                else:
                    # Atualizar status
                    db.execute('''
                        UPDATE instances 
                        SET status = 'connecting', last_updated = CURRENT_TIMESTAMP 
                        WHERE instance_name = ? AND lead_id = ?
                    ''', (instance_name, lead_id))
                    db.commit()
            except Exception as e:
                print(f"Erro ao salvar instância no banco: {e}")

        # Se temos credenciais para criar (do frontend de criação)
        identificacao = data.get('identificacao')
        if identificacao and lead_id:
            try:
                # Verificar se já existe credencial
                existing_cred = db.execute('SELECT id FROM credenciais WHERE instance_name = ?', 
                                         (instance_name,)).fetchone()
                
                if not existing_cred:
                    tipo = identificacao.get('tipo')
                    
                    if tipo == 'codigo':
                        db.execute('''
                            INSERT INTO credenciais (instance_name, lead_id, tipo, codigo, pin)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (
                            instance_name,
                            lead_id,
                            tipo,
                            identificacao.get('codigo'),
                            identificacao.get('pin')
                        ))
                    elif tipo == 'email':
                        db.execute('''
                            INSERT INTO credenciais (instance_name, lead_id, tipo)
                            VALUES (?, ?, ?)
                        ''', (instance_name, lead_id, tipo))
                    elif tipo == 'telefone':
                        db.execute('''
                            INSERT INTO credenciais (instance_name, lead_id, tipo, telefone, codigo_verificacao)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (
                            instance_name,
                            lead_id,
                            tipo,
                            identificacao.get('telefone'),
                            identificacao.get('codigo')
                        ))
                    
                    db.commit()
                    print(f"Credenciais tipo '{tipo}' criadas automaticamente para '{instance_name}'")
            except Exception as e:
                print(f"Aviso: Erro ao criar credenciais automaticamente: {e}")
                # Não interrompe o fluxo se falhar

        # Após a criação/verificação, verifica o status para saber se já está conectado ou precisa de QR
        state_data, state_code = verificar_status_interno(instance_name, lead_id) # Chama a função interna de status

        if state_code == 200:
             current_state = state_data.get('status')
             current_owner = state_data.get('owner')

             if current_state == 'open':
                  # Se já está conectado, salva no DB e retorna status conectado
                  print(f"Proxy <- Backend: Instância '{instance_name}' já conectada.")
                  # A função interna verificar_status_interno já salvou no DB
                  return jsonify({"status": current_state, "instanceName": instance_name, "owner": current_owner}), 200
             elif current_state in ['connecting', 'close', 'disconnected', 'qrcode', 'needs-code', 'scan-needed']: # Adiciona outros estados comuns que podem precisar de QR
                 # Se o status indica que precisa de QR ou está tentando conectar
                 print(f"Proxy <- Backend: Instância '{instance_name}' em estado '{current_state}'. Tentando obter QR Code.")
                 # Tenta obter o QR Code (lógica melhorada na make_evolution_request agora tenta /connect e /qrcode)
                 # Não precisamos chamar make_evolution_request diretamente aqui, pois o fluxo já tentou criar,
                 # e a próxima ação lógica é o frontend pedir o status periodicamente, que tentará obter o QR se o status for apropriado.
                 # No entanto, para a PRIMEIRA resposta após a criação, é bom tentar obter o QR imediatamente se o status indicar.

                 qr_response_data = None # Reinicia para esta tentativa específica
                 qr_status_code = None

                 # 1. Tenta o endpoint /instance/connect (muitas APIs retornam QR aqui)
                 connect_endpoint = f"/instance/connect/<instance_name>"
                 print(f"Proxy -> Evolution (Conectar): Tentando obter QR/Status via {connect_endpoint}")
                 connect_response_data, connect_status_code = make_evolution_request("GET", connect_endpoint, instance_name=instance_name)

                 if connect_status_code >= 200 and connect_status_code < 300:
                     # Verifica se a resposta contém dados de QR Code
                     if connect_response_data.get('base64') or connect_response_data.get('qrcode') or connect_response_data.get('qr') or connect_response_data.get('qrCode'):
                          qr_response_data = connect_response_data
                          qr_status_code = connect_status_code # Sinaliza que obteve QR
                     # Mesmo que não tenha QR, a resposta do /connect pode ter o status atualizado ou owner


                 # 2. Se o /connect não deu QR ou falhou, tenta o endpoint /instance/qrcode (original)
                 if not qr_response_data: # Só tenta se a primeira tentativa não deu QR
                     qr_endpoint_alt = f"/instance/qrcode/<instance_name>"
                     print(f"Proxy -> Evolution (Conectar): Tentando obter QR via {qr_endpoint_alt}")
                     qr_response_data_alt, qr_status_code_alt = make_evolution_request("GET", qr_endpoint_alt, instance_name=instance_name)

                     if qr_status_code_alt >= 200 and qr_status_code_alt < 300:
                          if qr_response_data_alt.get('base64') or qr_response_data_alt.get('qrcode') or qr_response_data_alt.get('qr') or qr_response_data_alt.get('qrCode'):
                               qr_response_data = qr_response_data_alt
                               qr_status_code = qr_status_code_alt # Sinaliza que obteve QR
                          # Se a resposta foi OK mas sem QR, não atualiza qr_response_data


                 if qr_response_data:
                      # Se obtivemos dados de QR Code
                      print(f"Proxy <- Backend: QR Code obtido para '{instance_name}'. Status atual: {current_state}.")
                       # Retorna o QR code e o status atual conhecido
                      return jsonify({"status": 'qrcode', "instanceName": instance_name, "owner": current_owner, "data": qr_response_data, "currentState": current_state}), 200 # Retorna 200
                 else:
                      # Se não está 'open' e NÃO conseguimos obter QR Code
                      print(f"Proxy <- Backend: Instância '{instance_name}' em estado '{current_state}', e não obteve QR Code.")
                      # Retorna o status atual conhecido, sem QR data
                      # O frontend vai continuar chamando /status periodicamente
                      return jsonify({"status": current_state, "instanceName": instance_name, "owner": current_owner, "error": "Não foi possível obter QR Code neste momento."}), 200 # Retorna 200


             else:
                  # Status desconhecido retornado pela verificação interna
                  print(f"Proxy <- Backend: Status desconhecido '{current_state}' para '{instance_name}' após criação/verificação.")
                  return jsonify({"status": current_state, "instanceName": instance_name, "owner": current_owner, "message": "Status desconhecido retornado."}), 200 # Retorna 200

        else:
            # Falha ao verificar status após criação/verificação
            print(f"Proxy <- Backend: Falha ao verificar status para '{instance_name}' após criação/verificação ({state_code}).")
            # Retorna o erro da verificação de status
            return jsonify(state_data), state_code # state_data já contém o erro


    else:
        # --- Regra 2: Erro na Criação (Exceto Nome em Uso) ---
        print(f"Proxy <- Backend: Erro genérico na criação da instância '{instance_name}': {status_code}")
        # Retorna o erro original da tentativa de criação
        # response_data já contém os detalhes do erro formatados pela make_evolution_request
        return jsonify(response_data), status_code


@app.route('/api/lead/status/<instance_name>', methods=['GET'])
def verificar_status_externo(instance_name):
    """
    Endpoint para o frontend verificar o status da conexão periodicamente.
    Chama a função interna de verificação de status.
    """
    if not instance_name:
         print("Proxy <- Backend: Nome da instância ausente na requisição /status.")
         return jsonify({"error": "Nome da instância é obrigatório na URL."}), 400

    lead_id = request.headers.get('X-Lead-Id')
    print(f"Proxy -> Backend: Recebida requisição /status para instância: '{instance_name}' (Lead ID: {lead_id})")
    
    # A função interna já retorna a tupla (response_data, status_code)
    response_data, status_code = verificar_status_interno(instance_name, lead_id)
    return jsonify(response_data), status_code

def verificar_status_interno(instance_name, lead_id=None):
    """
    Função interna para obter o status de conexão de uma instância.
    Pode ser chamada por outros endpoints no backend.
    Se o status for 'open', salva/atualiza no DB.
    Retorna (response_data, status_code) tuple.
    """
    print(f"Proxy -> Backend(Internal): Verificando status interno para '{instance_name}'.")
    
    # Se temos lead_id, verificar se a instância pertence ao lead
    if lead_id:
        db = get_db()
        try:
            cursor = db.execute('SELECT * FROM instances WHERE instance_name = ? AND lead_id = ?', 
                              (instance_name, lead_id))
            instance = cursor.fetchone()
            
            if not instance:
                print(f"Proxy <- Backend(Internal): Instância '{instance_name}' não pertence ao lead {lead_id}")
                # Não retornar erro aqui, pois pode ser uma instância global ou recém criada
        except Exception as e:
            print(f"Erro ao verificar propriedade da instância: {e}")
    
    # 1. Tenta o endpoint direto de connectionState
    status_endpoint_state = f"/instance/connectionState/<instance_name>"
    state_response_data, state_status_code = make_evolution_request("GET", status_endpoint_state, instance_name=instance_name)

    if state_status_code >= 200 and state_status_code < 300 and state_response_data.get('instance'):
        # Sucesso ao obter status pelo connectionState
        instance_info = state_response_data.get('instance', {})
        state = instance_info.get('state') or instance_info.get('connectionStatus') or 'unknown'
        owner = instance_info.get('owner') or instance_info.get('profilePictureUrl') # Alguns APIs retornam owner em profilePictureUrl
        print(f"Proxy <- Backend(Internal): Status para '{instance_name}' via connectionState: {state} (Owner: {owner}).")

        # Se o status for 'open' ou 'connecting' (para persistir que está tentando), salva no banco de dados
        # Decidi salvar 'connecting' também para o lead saber que a instância existe e está ativa.
        if state in ['open', 'connecting']:
             save_instance_status(instance_name, state, owner, lead_id)

         # Retorna o status e o owner
        return {"status": state, "instanceName": instance_name, "owner": owner}, 200
    else:
        # Falhou no connectionState, tenta buscar na lista geral
        print(f"Proxy <- Backend(Internal): Não obteve status via connectionState ({state_status_code}). Tentando fetchInstances...")
        fetch_endpoint = "/instance/fetchInstances"
        fetch_response_data, fetch_status_code = make_evolution_request("GET", fetch_endpoint)

        if fetch_status_code >= 200 and fetch_status_code < 300 and isinstance(fetch_response_data, list):
            # Sucesso ao obter lista de instâncias
            found_instance = None
            for inst in fetch_response_data:
                # Verifica diferentes nomes de campos para o nome da instância
                if inst.get('name') == instance_name or inst.get('instanceName') == instance_name:
                    found_instance = inst
                    break

            if found_instance:
                # Instância encontrada na lista
                state = found_instance.get('connectionStatus') or found_instance.get('state') or 'unknown'
                owner = found_instance.get('owner') or found_instance.get('profilePictureUrl')
                print(f"Proxy <- Backend(Internal): Status para '{instance_name}' via fetchInstances: {state} (Owner: {owner}).")

                # Se o status for 'open' ou 'connecting', salva no banco de dados
                if state in ['open', 'connecting']:
                    save_instance_status(instance_name, state, owner, lead_id)

                 # Retorna o status e owner
                return {"status": state, "instanceName": instance_name, "owner": owner}, 200
            else:
                # Instância não encontrada na lista general
                print(f"Proxy <- Backend(Internal): Instância '{instance_name}' não encontrada em fetchInstances.")
                # Podemos verificar no nosso DB se tínhamos informações salvas antes
                db_instance = get_instance_from_db(instance_name)
                if db_instance:
                     print(f"Proxy <- Backend(Internal): Instância '{instance_name}' encontrada no DB local (último status: {db_instance['status']}).")
                     # Retorna o último status conhecido do DB como fallback
                     # O status aqui pode ser qualquer coisa salva antes (open, close, etc.)
                     return {"status": db_instance['status'], "instanceName": instance_name, "owner": db_instance['evolution_owner'], "from_db": True, "message": "Status obtido do banco de dados local (API não retornou)."}, 200

                else:
                    # Instância não encontrada em nenhum lugar
                    print(f"Proxy <- Backend(Internal): Instância '{instance_name}' não encontrada no Evolution API nem no DB local.")
                    return {"status": "not_found", "error": f"Instância '{instance_name}' não encontrada."}, 404
        else:
            # Falhou tanto no connectionState quanto em fetchInstances
            print(f"Proxy <- Backend(Internal): Falha geral ao obter status via Evolution API para '{instance_name}'.")
            # Tenta retornar o último status conhecido do nosso DB como fallback
            db_instance = get_instance_from_db(instance_name)
            if db_instance:
                 print(f"Proxy <- Backend(Internal): Instância '{instance_name}' encontrada no DB local (último status: {db_instance['status']}).")
                 # Retorna o último status conhecido do DB como fallback
                 return {"status": db_instance['status'], "instanceName": instance_name, "owner": db_instance['evolution_owner'], "from_db": True, "message": "Status obtido do banco de dados local (API não retornou)."}, 200
            else:
                # Falhou geral e não encontrou no DB
                print(f"Proxy <- Backend(Internal): Falha geral e instância '{instance_name}' não encontrada no DB local.")
                error_message = state_response_data.get('error') or fetch_response_data.get('error') or "Não foi possível obter o status da instância."
                # Decide qual status HTTP retornar, preferindo o da Evolution API se disponível e for erro, caso contrário, 500.
                status_to_return = state_status_code if state_status_code is not None and state_status_code >= 400 else (fetch_status_code if fetch_status_code is not None and fetch_status_code >= 400 else 500)
                # Se os status_code foram None (erro de conexão no make_evolution_request), use 500
                if status_to_return is None or status_to_return < 400:
                    status_to_return = 500

                return {"status": "error", "error": error_message}, status_to_return


# --- NOVO: Endpoint para obter informações do lead e suas instâncias ---
@app.route('/api/lead/info', methods=['GET'])
def get_lead_info():
    """Retorna informações do lead e suas instâncias."""
    lead_id = request.headers.get('X-Lead-Id')
    
    if not lead_id:
        return jsonify({'error': 'Lead ID não fornecido'}), 401
    
    db = get_db()
    try:
        # Buscar informações do lead e plano
        cursor = db.execute('''
            SELECT l.*, p.name as plan_name, p.max_instances, p.message_limit_per_month
            FROM leads l
            LEFT JOIN plans p ON l.plan_id = p.id
            WHERE l.id = ? AND l.is_active = 1
        ''', (lead_id,))
        
        lead = cursor.fetchone()
        if not lead:
            return jsonify({'error': 'Lead não encontrado'}), 404
        
        # Buscar todas as instâncias do lead
        instances_cursor = db.execute('''
            SELECT * FROM instances 
            WHERE lead_id = ? 
            ORDER BY created_at DESC
        ''', (lead_id,))
        
        instances = instances_cursor.fetchall()
        
        # Converter para lista de dicionários
        instances_list = []
        for inst in instances:
            instances_list.append({
                'id': inst['id'],
                'instance_name': inst['instance_name'],
                'status': inst['status'],
                'evolution_owner': inst['evolution_owner'],
                'created_at': inst['created_at'],
                'last_updated': inst['last_updated']
            })
        
        return jsonify({
            'lead_id': lead['id'],
            'lead_name': lead['name'],
            'plan_name': lead['plan_name'] or 'Plano Gratuito',
            'max_instances': lead['max_instances'] or 1,
            'message_limit': lead['message_limit_per_month'] or -1,
            'instances': instances_list
        }), 200
        
    except Exception as e:
        print(f"Erro ao buscar informações do lead: {e}")
        traceback.print_exc()
        return jsonify({'error': 'Erro ao buscar informações'}), 500


# --- NOVO: Endpoint para desconectar instância ---
@app.route('/api/lead/disconnect/<instance_name>', methods=['POST'])
def disconnect_instance(instance_name):
    """Desconecta uma instância do WhatsApp."""
    lead_id = request.headers.get('X-Lead-Id')
    
    if not lead_id:
        return jsonify({'error': 'Lead ID não fornecido'}), 401
    
    # Verificar se a instância pertence ao lead
    db = get_db()
    try:
        cursor = db.execute('SELECT * FROM instances WHERE instance_name = ? AND lead_id = ?', 
                           (instance_name, lead_id))
        
        if not cursor.fetchone():
            return jsonify({'error': 'Instância não encontrada'}), 404
        
        # Chamar Evolution API para desconectar
        logout_endpoint = f"/instance/logout/<instance_name>"
        response_data, status_code = make_evolution_request("DELETE", logout_endpoint, instance_name=instance_name)
        
        # Atualizar status no banco independente do resultado
        db.execute('''
            UPDATE instances 
            SET status = 'disconnected', last_updated = CURRENT_TIMESTAMP 
            WHERE instance_name = ?
        ''', (instance_name,))
        db.commit()
        
        if status_code >= 200 and status_code < 300:
            return jsonify({'message': 'Instância desconectada com sucesso'}), 200
        else:
            # Mesmo com erro, retorna sucesso pois atualizamos o banco
            return jsonify({'message': 'Instância marcada como desconectada', 'warning': 'Pode haver erro na API Evolution'}), 200
            
    except Exception as e:
        print(f"Erro ao desconectar instância: {e}")
        traceback.print_exc()
        return jsonify({'error': 'Erro ao desconectar instância'}), 500


# --- NOVO: Endpoint para deletar instância ---
@app.route('/api/lead/delete/<instance_name>', methods=['DELETE'])
def delete_instance(instance_name):
    """Deleta uma instância completamente."""
    lead_id = request.headers.get('X-Lead-Id')
    
    if not lead_id:
        return jsonify({'error': 'Lead ID não fornecido'}), 401
    
    db = get_db()
    try:
        # Verificar se a instância pertence ao lead
        cursor = db.execute('SELECT * FROM instances WHERE instance_name = ? AND lead_id = ?', 
                           (instance_name, lead_id))
        
        if not cursor.fetchone():
            return jsonify({'error': 'Instância não encontrada'}), 404
        
        # Tentar deletar da Evolution API
        delete_endpoint = f"/instance/delete/<instance_name>"
        response_data, status_code = make_evolution_request("DELETE", delete_endpoint, instance_name=instance_name)
        
        # Deletar do banco independente do resultado da API
        db.execute('DELETE FROM instances WHERE instance_name = ?', (instance_name,))
        db.commit()
        
        return jsonify({'message': 'Instância deletada com sucesso'}), 200
        
    except Exception as e:
        print(f"Erro ao deletar instância: {e}")
        traceback.print_exc()
        return jsonify({'error': 'Erro ao deletar instância'}), 500


# --- Endpoints para o Frontend do Disparador (`disparador_lead.html` - Futuro) ---

@app.route('/api/lead/disparar', methods=['POST'])
def disparar_mensagens():
    """
    Endpoint para receber requisição de disparo do frontend do disparador.
    Implementar lógica de validação de plano/uso aqui antes de chamar a Evolution API.
    """
    data = request.json
    lead_id = request.headers.get('X-Lead-Id')
    
    if not lead_id:
        return jsonify({'error': 'Lead ID não fornecido'}), 401
    
    # Validar dados recebidos
    instance_name = data.get('instanceName')
    number = data.get('number')
    message = data.get('message')
    mentions_everyone = data.get('mentionsEveryone', False)
    
    if not all([instance_name, number, message]):
        return jsonify({'error': 'instanceName, number e message são obrigatórios'}), 400
    
    # Verificar se a instância pertence ao lead
    db = get_db()
    try:
        cursor = db.execute('SELECT * FROM instances WHERE instance_name = ? AND lead_id = ?', 
                           (instance_name, lead_id))
        
        if not cursor.fetchone():
            return jsonify({'error': 'Instância não autorizada'}), 403
        
        # TODO: Implementar verificação de limites do plano aqui
        # - Verificar message_limit_per_month
        # - Atualizar contador de mensagens
        
        # Por enquanto, apenas encaminha para a Evolution API
        # Determinar o tipo de mensagem baseado no formato
        message_type = message.get('tipo', 'texto')
        
        if message_type == 'texto':
            # Mensagem de texto simples
            send_endpoint = f"/message/sendText/<instance_name>"
            payload = {
                "number": number,
                "text": message.get('conteudo', ''),
                "delay": 1000  # 1 segundo de delay
            }
            
            # Se for grupo e mentions_everyone está ativo
            if mentions_everyone and '@g.us' in number:
                payload['mentionsEveryOne'] = True
                
        elif message_type == 'imagem':
            # Mensagem com imagem
            send_endpoint = f"/message/sendMedia/<instance_name>"
            payload = {
                "number": number,
                "mediatype": "image",
                "media": message.get('conteudo', ''),
                "caption": message.get('caption', '')
            }
            
        elif message_type == 'video':
            # Mensagem com vídeo
            send_endpoint = f"/message/sendMedia/<instance_name>"
            payload = {
                "number": number,
                "mediatype": "video",
                "media": message.get('conteudo', ''),
                "caption": message.get('caption', '')
            }
            
        elif message_type == 'audio':
            # Mensagem com áudio
            send_endpoint = f"/message/sendMedia/<instance_name>"
            payload = {
                "number": number,
                "mediatype": "audio",
                "media": message.get('conteudo', '')
            }
        else:
            return jsonify({'error': f'Tipo de mensagem não suportado: {message_type}'}), 400
        
        # Enviar mensagem via Evolution API
        response_data, status_code = make_evolution_request("POST", send_endpoint, instance_name=instance_name, json_data=payload)
        
        if status_code >= 200 and status_code < 300:
            # Atualizar contador de mensagens do mês (TODO)
            # db.execute('UPDATE instances SET message_count_current_month = message_count_current_month + 1 WHERE instance_name = ?', (instance_name,))
            # db.commit()
            
            return jsonify({'message': 'Mensagem enviada com sucesso', 'data': response_data}), 200
        else:
            return jsonify({'error': 'Erro ao enviar mensagem', 'detail': response_data}), status_code
            
    except Exception as e:
        print(f"Erro ao disparar mensagem: {e}")
        traceback.print_exc()
        return jsonify({'error': 'Erro interno ao processar disparo'}), 500

# --- SISTEMA DE CREDENCIAIS PARA LEADS ---

@app.route('/api/lead/criar-credencial', methods=['POST'])
def criar_credencial():
    """Cria credenciais de acesso para uma instância."""
    data = request.json
    instance_name = data.get('instanceName')
    identificacao = data.get('identificacao')
    lead_info = data.get('leadInfo')
    
    if not all([instance_name, identificacao]):
        return jsonify({'error': 'instanceName e identificacao são obrigatórios'}), 400
    
    db = get_db()
    try:
        # Primeiro verifica se a instância existe
        instance = db.execute('SELECT * FROM instances WHERE instance_name = ?', 
                            (instance_name,)).fetchone()
        
        if not instance:
            return jsonify({'error': 'Instância não encontrada'}), 404
        
        lead_id = instance['lead_id']
        
        # Verifica se já existe credencial para esta instância
        existing = db.execute('SELECT * FROM credenciais WHERE instance_name = ?', 
                            (instance_name,)).fetchone()
        
        if existing:
            return jsonify({'error': 'Já existem credenciais para esta instância'}), 409
        
        # Cria credencial baseada no tipo
        tipo = identificacao.get('tipo')
        
        if tipo == 'codigo':
            db.execute('''
                INSERT INTO credenciais (instance_name, lead_id, tipo, codigo, pin)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                instance_name,
                lead_id,
                tipo,
                identificacao.get('codigo'),
                identificacao.get('pin')
            ))
            
        elif tipo == 'email':
            # Para tipo email, não precisamos armazenar senha aqui pois já está na tabela leads
            db.execute('''
                INSERT INTO credenciais (instance_name, lead_id, tipo)
                VALUES (?, ?, ?)
            ''', (instance_name, lead_id, tipo))
            
        elif tipo == 'telefone':
            db.execute('''
                INSERT INTO credenciais (instance_name, lead_id, tipo, telefone, codigo_verificacao)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                instance_name,
                lead_id,
                tipo,
                identificacao.get('telefone'),
                identificacao.get('codigo')
            ))
        else:
            return jsonify({'error': 'Tipo de credencial inválido'}), 400
        
        db.commit()
        
        print(f"Credenciais criadas para instância '{instance_name}' - Tipo: {tipo}")
        return jsonify({
            'message': 'Credenciais criadas com sucesso',
            'instanceName': instance_name,
            'tipo': tipo
        }), 201
        
    except Exception as e:
        print(f"Erro ao criar credenciais: {e}")
        traceback.print_exc()
        return jsonify({'error': 'Erro ao criar credenciais'}), 500


@app.route('/api/lead/verificar-credenciais', methods=['POST'])
def verificar_credenciais():
    """Verifica credenciais e retorna informações da instância."""
    data = request.json
    tipo = data.get('tipo')
    
    if not tipo:
        return jsonify({'error': 'Tipo de credencial é obrigatório'}), 400
    
    db = get_db()
    try:
        result = None
        
        if tipo == 'codigo':
            codigo = data.get('codigo')
            pin = data.get('pin')
            
            if not all([codigo, pin]):
                return jsonify({'error': 'Código e PIN são obrigatórios'}), 400
            
            result = db.execute('''
                SELECT c.*, l.name as lead_name, l.email as lead_email,
                       i.status as instance_status, i.evolution_owner
                FROM credenciais c
                JOIN leads l ON c.lead_id = l.id
                JOIN instances i ON c.instance_name = i.instance_name
                WHERE c.codigo = ? AND c.pin = ? AND c.tipo = 'codigo' 
                      AND c.status = 'ativo' AND l.is_active = 1
            ''', (codigo, pin)).fetchone()
            
        elif tipo == 'email':
            email = data.get('email')
            senha = data.get('senha')
            
            if not all([email, senha]):
                return jsonify({'error': 'Email e senha são obrigatórios'}), 400
            
            # Primeiro verifica o lead
            lead = db.execute('''
                SELECT id, password FROM leads 
                WHERE email = ? AND is_active = 1
            ''', (email,)).fetchone()
            
            if lead and lead['password'] == senha:  # Em produção, use hash!
                # Busca credencial tipo email para este lead
                result = db.execute('''
                    SELECT c.*, l.name as lead_name, l.email as lead_email,
                           i.status as instance_status, i.evolution_owner
                    FROM credenciais c
                    JOIN leads l ON c.lead_id = l.id
                    JOIN instances i ON c.instance_name = i.instance_name
                    WHERE c.lead_id = ? AND c.tipo = 'email' AND c.status = 'ativo'
                    ORDER BY c.criado_em DESC
                    LIMIT 1
                ''', (lead['id'],)).fetchone()
            
        elif tipo == 'telefone':
            telefone = data.get('telefone')
            codigo_verificacao = data.get('codigo')
            
            if not all([telefone, codigo_verificacao]):
                return jsonify({'error': 'Telefone e código são obrigatórios'}), 400
            
            # Remove formatação do telefone
            telefone_limpo = ''.join(filter(str.isdigit, telefone))
            
            result = db.execute('''
                SELECT c.*, l.name as lead_name, l.email as lead_email,
                       i.status as instance_status, i.evolution_owner
                FROM credenciais c
                JOIN leads l ON c.lead_id = l.id
                JOIN instances i ON c.instance_name = i.instance_name
                WHERE c.telefone = ? AND c.codigo_verificacao = ? 
                      AND c.tipo = 'telefone' AND c.status = 'ativo' 
                      AND l.is_active = 1
            ''', (telefone_limpo, codigo_verificacao)).fetchone()
        
        if result:
            # Atualiza último acesso
            db.execute('''
                UPDATE credenciais 
                SET ultimo_acesso = CURRENT_TIMESTAMP,
                    tentativas_falhas = 0
                WHERE id = ?
            ''', (result['id'],))
            db.commit()
            
            # Verifica status da instância na Evolution
            instance_data, status_code = verificar_status_interno(
                result['instance_name'], 
                result['lead_id']
            )
            
            return jsonify({
                'success': True,
                'instanceName': result['instance_name'],
                'leadName': result['lead_name'],
                'leadId': result['lead_id'],
                'instanceStatus': instance_data.get('status', 'unknown'),
                'owner': instance_data.get('owner'),
                'message': 'Credenciais válidas'
            }), 200
        else:
            # Incrementa tentativas falhas (implementar lógica de bloqueio se necessário)
            return jsonify({
                'success': False,
                'error': 'Credenciais inválidas'
            }), 401
            
    except Exception as e:
        print(f"Erro ao verificar credenciais: {e}")
        traceback.print_exc()
        return jsonify({'error': 'Erro ao verificar credenciais'}), 500


@app.route('/api/lead/minhas-credenciais', methods=['GET'])
def minhas_credenciais():
    """Retorna as credenciais de um lead autenticado."""
    lead_id = request.headers.get('X-Lead-Id')
    
    if not lead_id:
        return jsonify({'error': 'Lead não autenticado'}), 401
    
    db = get_db()
    try:
        credenciais = db.execute('''
            SELECT c.*, i.status as instance_status
            FROM credenciais c
            JOIN instances i ON c.instance_name = i.instance_name
            WHERE c.lead_id = ? AND c.status = 'ativo'
            ORDER BY c.criado_em DESC
        ''', (lead_id,)).fetchall()
        
        creds_list = []
        for cred in credenciais:
            cred_info = {
                'instanceName': cred['instance_name'],
                'tipo': cred['tipo'],
                'criadoEm': cred['criado_em'],
                'ultimoAcesso': cred['ultimo_acesso'],
                'instanceStatus': cred['instance_status']
            }
            
            # Adiciona campos específicos do tipo
            if cred['tipo'] == 'codigo':
                cred_info['codigo'] = cred['codigo']
                # Não retorna o PIN por segurança
            elif cred['tipo'] == 'telefone':
                cred_info['telefone'] = cred['telefone']
                # Não retorna o código de verificação
                
            creds_list.append(cred_info)
        
        return jsonify(creds_list), 200
        
    except Exception as e:
        print(f"Erro ao buscar credenciais: {e}")
        return jsonify({'error': 'Erro ao buscar credenciais'}), 500


# --- Endpoint para buscar grupos (para o disparador) ---
@app.route('/api/lead/grupos/<instance_name>', methods=['GET'])
def buscar_grupos_lead(instance_name):
    """
    Endpoint para buscar grupos de uma instância específica via backend.
    Filtra dados se necessário e pode verificar permissões do lead.
    """
    if not instance_name:
         print("Proxy <- Backend: Nome da instância ausente na requisição /grupos.")
         return jsonify({"error": "Nome da instância é obrigatório na URL."}), 400

    lead_id = request.headers.get('X-Lead-Id')
    
    # Verificar se a instância pertence ao lead
    if lead_id:
        db = get_db()
        try:
            cursor = db.execute('SELECT * FROM instances WHERE instance_name = ? AND lead_id = ?', 
                               (instance_name, lead_id))
            
            if not cursor.fetchone():
                return jsonify({'error': 'Instância não autorizada'}), 403
        except Exception as e:
            print(f"Erro ao verificar autorização: {e}")

    print(f"Proxy -> Backend: Recebida requisição /grupos para instância: '{instance_name}'")

    # Exemplo de chamada para a Evolution API:
    endpoints_to_try = [
        f"/group/fetchAllGroups/<instance_name>?getParticipants=false", # Evolução API endpoint
        f"/groups/<instance_name>", # Possível endpoint alternativo
        f"/instance/groups/<instance_name>" # Outro possível endpoint
    ]

    for endpoint_template in endpoints_to_try:
        response_data, status_code = make_evolution_request("GET", endpoint_template, instance_name=instance_name)

        if status_code >= 200 and status_code < 300: # Sucesso ou redirecionamento/info (2xx)
             if isinstance(response_data, list): # Verifica se a resposta é uma lista de grupos
                 # Sucesso! Retorna a lista de grupos (pode filtrar campos aqui se necessário)
                 print(f"Proxy <- Backend: Grupos obtidos para '{instance_name}' via {endpoint_template}.")
                 # Retorna os dados brutos dos grupos por enquanto.
                 # Futuramente, pode filtrar campos ou adicionar lógica de permissão do lead aqui.
                 return jsonify(response_data), 200
             else:
                  # Resposta OK, mas não é uma lista no formato esperado de grupos
                  print(f"Proxy <- Backend: Endpoint {endpoint_template} retornou OK ({status_code}), mas a resposta não é uma lista.")
                  # Continua tentando os próximos endpoints templates
                  continue # Tenta o próximo endpoint_template

        elif status_code is not None and status_code == 404:
             print(f"Proxy <- Backend: Endpoint {endpoint_template} não encontrado ou instância sem grupos para '{instance_name}'.")
             continue # Tenta o próximo endpoint
        else:
             # Se houver um erro que não seja 404, ou erro de conexão, retorna-o imediatamente
             print(f"Proxy <- Backend: Erro ao buscar grupos via {endpoint_template} ({status_code}).")
             # response_data já contém o erro formatado pela make_evolution_request
             return jsonify(response_data), status_code

    # Se nenhum endpoint funcionou ou encontrou uma lista de grupos
    print(f"Proxy <- Backend: Falha ao encontrar endpoint funcional ou lista de grupos para '{instance_name}'.")
    return jsonify({"error": f"Não foi possível obter a lista de grupos para a instância '{instance_name}'."}, 500)


# --- Endpoint para extrair participantes de um grupo (para o disparador) ---
# Usa <path:group_jid> na URL para permitir caracteres como '/' e ':' que podem estar no JID
@app.route('/api/lead/participantes/<instance_name>/<path:group_jid>', methods=['GET'])
def extrair_participantes_lead(instance_name, group_jid):
     """
     Endpoint para extrair participantes de um grupo específico via backend.
     """
     if not instance_name or not group_jid:
          print("Proxy <- Backend: Nome da instância ou JID do grupo ausente na requisição /participantes.")
          return jsonify({"error": "Nome da instância e JID do grupo são obrigatórios na URL."}), 400

     lead_id = request.headers.get('X-Lead-Id')
     
     # Verificar se a instância pertence ao lead
     if lead_id:
         db = get_db()
         try:
             cursor = db.execute('SELECT * FROM instances WHERE instance_name = ? AND lead_id = ?', 
                                (instance_name, lead_id))
             
             if not cursor.fetchone():
                 return jsonify({'error': 'Instância não autorizada'}), 403
         except Exception as e:
             print(f"Erro ao verificar autorização: {e}")

     print(f"Proxy -> Backend: Recebida requisição /participantes para instância: '{instance_name}' e grupo: '{group_jid}'")

     # Sanitiza o nome da instância recebido na URL
     sanitized_instance_name = "".join(c if c.isalnum() or c == '-' else '-' for c in instance_name.lower()).strip('-')
     if not sanitized_instance_name:
          print(f"Proxy <- Backend: Nome da instância '{instance_name}' na URL resultou em nome sanitizado vazio.")
          return jsonify({"error": "Nome da instância inválido na URL."}), 400
     instance_name_for_api = sanitized_instance_name


     # Exemplo de chamada para a Evolution API:
     # Podemos usar diferentes endpoints
     endpoints_to_try = [
          f"/group/participants/<instance_name>?groupJid={urllib.parse.quote(group_jid)}", # Endpoint comum, JID encodado
          f"/group/fetchAllGroups/<instance_name>?getParticipants=true", # Buscar na lista geral com participantes
     ]

     for endpoint_template in endpoints_to_try:
          # Para o fetchAllGroups, o JID do grupo não vai na URL do endpoint template,
          # apenas o instance_name (que make_evolution_request encoda).
          # A filtragem/busca pelo group_jid ocorre na lógica após a chamada.
          # Para o /group/participants, o JID JÁ VAI no endpoint_template (pré-encodado aqui).
          endpoint = endpoint_template # O template já está pronto para ser usado pelo make_evolution_request


          response_data, status_code = make_evolution_request("GET", endpoint, instance_name=instance_name_for_api) # Usa o nome sanitizado

          if status_code is not None and status_code >= 200 and status_code < 300:
              # Sucesso! Tenta encontrar a lista de participantes nos diferentes formatos de resposta
              participants = []
              # Verifica qual endpoint_template foi usado para saber como processar a resposta
              if "fetchAllGroups" in endpoint_template:
                  # Se foi fetchAllGroups, a resposta é uma lista de grupos.
                  if isinstance(response_data, list):
                      # Procura o grupo específico na lista
                      found_group = next((g for g in response_data if g.get('id') == group_jid or g.get('jid') == group_jid or g.get('remoteJid') == group_jid), None)
                      if found_group and found_group.get('participants'):
                           participants = found_group['participants']
                           print(f"Proxy <- Backend: Participantes obtidos para '{group_jid}' via {endpoint_template} (fetchAllGroups).")
                  # else: response_data foi uma lista, mas não encontrou o grupo ou ele não tem participants. participants[] fica vazio.
              else: # Assume que é o endpoint /group/participants direto
                  # A resposta pode ser uma lista direta ou um dicionário com 'participants'
                  if isinstance(response_data, list):
                      participants = response_data
                      print(f"Proxy <- Backend: Participantes obtidos para '{group_jid}' via {endpoint_template} (direct list).")
                  elif isinstance(response_data, dict) and response_data.get('participants'):
                       participants = response_data['participants']
                       print(f"Proxy <- Backend: Participantes obtidos para '{group_jid}' via {endpoint_template} (encapsulated).")
                  # else: response_data foi OK, mas não é lista nem tem 'participants'. participants[] fica vazio.


              # Processa a lista de participantes para extrair apenas os IDs/JIDs
              if participants is not None and len(participants) > 0:
                   # Extrai o ID/JID de cada participante, que pode estar em diferentes campos
                   participant_jids = []
                   for p in participants:
                       if isinstance(p, dict):
                           jid = p.get('id') or p.get('jid') or p.get('participant') or p.get('jid_usuario') # Adiciona jid_usuario, comum em algumas APIs
                           if jid: participant_jids.append(str(jid)) # Garante que é string
                       elif isinstance(p, str):
                           # Se o item da lista é apenas a string do JID/número
                           if p: participant_jids.append(p) # Já é string

                   # Opcional: Garantir o formato @s.whatsapp.net para números individuais se necessário
                   processed_jids = []
                   for jid in participant_jids:
                        if isinstance(jid, str):
                           # Verifica se é um número (apenas dígitos) e não é um JID de grupo (@g.us)
                           if '@' not in jid and jid.isdigit() and not jid.endswith('g.us'): # Evita adicionar @s.whatsapp.net para grupos
                               processed_jids.append(f"{jid}@s.whatsapp.net")
                           else:
                               processed_jids.append(jid) # Já tem @, ou não é só dígito, ou é grupo JID

                   print(f"Proxy <- Backend: {len(processed_jids)} participantes processados para '{group_jid}'.")
                   # Retorna a lista de JIDs processada
                   return jsonify(processed_jids), 200
              else:
                  # Resposta OK, mas não encontrou a lista de participantes no formato esperado ou lista vazia
                  print(f"Proxy <- Backend: Endpoint {endpoint_template} retornou OK ({status_code}), mas sem lista de participantes ou lista vazia para '{group_jid}'.")
                  # Continua tentando os próximos endpoints templates
                  continue # Tenta o próximo endpoint_template

          elif status_code is not None and status_code == 404:
               print(f"Proxy <- Backend: Endpoint {endpoint_template} não encontrado ou grupo '{group_jid}' não encontrado.")
               continue # Tenta o próximo endpoint
          else:
               print(f"Proxy <- Backend: Erro ao extrair participantes via {endpoint_template} ({status_code}).")
               # Se houver um erro que não seja 404, ou erro de conexão, retorna-o imediatamente
               # response_data já contém o erro formatado pela make_evolution_request
               return jsonify(response_data), status_code

     # Se nenhum endpoint funcionou ou encontrou participantes
     print(f"Proxy <- Backend: Falha ao encontrar endpoint funcional ou participantes para o grupo '{group_jid}'.")
     return jsonify({"error": f"Não foi possível extrair participantes para o grupo '{group_jid}'."}, 500)


# --- Endpoint de Teste (Opcional) ---
@app.route('/')
def index():
    return "Backend TASK AI rodando! Acesse /api/lead/conectar ou outros endpoints."

# --- CONFIGURAÇÕES DE ADMINISTRAÇÃO ---
ADMIN_TOKEN = "SEU_TOKEN_ADMIN_SUPER_SECRETO_AQUI_12345"  # MUDE ISSO EM PRODUÇÃO!

# Decorador para proteger endpoints administrativos
from functools import wraps

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('X-Admin-Token')
        if token != ADMIN_TOKEN:
            return jsonify({"error": "Token de administrador inválido ou ausente."}), 401
        return f(*args, **kwargs)
    return decorated_function

# --- Endpoint de Login para Leads (`lead_login.html`) ---
@app.route('/api/lead/login', methods=['POST'])
def lead_login():
    """Verifica as credenciais do lead (email/senha) e retorna informações do lead."""
    data = request.json
    email = data.get('email')
    password = data.get('password')  # !!! Lembre-se: senha em texto puro é INSEGURO !!!

    if not email or not password:
        print("Proxy <- Backend: Tentativa de login do lead sem email ou senha.")
        return jsonify({"error": "Email e senha são obrigatórios."}), 400

    db = get_db()
    try:
        # Busca o lead pelo email
        cursor = db.execute("SELECT id, name, email, password, plan_id, plan_expiration_date, is_active FROM leads WHERE email = ?", (email,))
        lead = cursor.fetchone()

        if lead:
            # Verifica se a senha corresponde (!!! EM PRODUÇÃO, USE HASHING SEGURO !!!)
            if lead['password'] == password:  # Comparação de texto puro (INSEGURO!)
                # Verifica se o lead está ativo
                if not lead['is_active']:
                    print(f"Proxy <- Backend: Login falhou para lead '{email}': Lead inativo.")
                    return jsonify({"error": "Sua conta está inativa. Entre em contato com o administrador.", "authenticated": False}), 403

                print(f"Proxy <- Backend: Login bem-sucedido para lead '{email}'.")

                # Busca a instância associada a este lead
                instance_cursor = db.execute("SELECT instance_name FROM instances WHERE lead_id = ? LIMIT 1", (lead['id'],))
                instance = instance_cursor.fetchone()

                # Prepara a resposta
                response_data = {
                    "message": "Login bem-sucedido.",
                    "authenticated": True,
                    "lead_id": lead['id'],
                    "lead_name": lead['name'],
                    "lead_email": lead['email'],
                    "instance_name": instance['instance_name'] if instance else None,
                    "plan_id": lead['plan_id'],
                    "plan_expiration_date": lead['plan_expiration_date'],
                    "is_active": bool(lead['is_active'])
                }
                return jsonify(response_data), 200

            else:
                print(f"Proxy <- Backend: Login falhou para lead '{email}': Senha incorreta.")
                return jsonify({"error": "Credenciais inválidas.", "authenticated": False}), 401
        else:
            print(f"Proxy <- Backend: Login falhou: Lead com email '{email}' não encontrado.")
            return jsonify({"error": "Credenciais inválidas.", "authenticated": False}), 401

    except Exception as e:
        print(f"ERRO BD: Falha no login do lead para email '{email}': {e}")
        traceback.print_exc()
        return jsonify({"error": "Erro interno ao tentar fazer login."}), 500

# --- Endpoint de Registro de Leads ---
@app.route('/api/lead/register', methods=['POST'])
def lead_register():
    """Registra um novo lead (auto-cadastro)."""
    data = request.json
    name = data.get('name')
    email = data.get('email')
    phone = data.get('phone')
    password = data.get('password')

    if not all([name, email, password]):
        return jsonify({"error": "Nome, email e senha são obrigatórios."}), 400

    db = get_db()
    try:
        # Verifica se o email já existe
        existing = db.execute("SELECT id FROM leads WHERE email = ?", (email,)).fetchone()
        if existing:
            return jsonify({"error": "Este email já está cadastrado."}), 400

        # Cria o lead como INATIVO (precisa aprovação do admin)
        cursor = db.execute("""
            INSERT INTO leads (name, email, phone, password, plan_id, is_active)
            VALUES (?, ?, ?, ?, 1, 0)
        """, (name, email, phone, password))
        
        lead_id = cursor.lastrowid
        db.commit()

        # NÃO cria mais instância automaticamente para o lead
        # As instâncias serão criadas manualmente pelo lead após aprovação

        print(f"Novo lead registrado: {name} ({email}) - ID: {lead_id}")
        return jsonify({
            "message": "Cadastro realizado com sucesso! Aguarde aprovação.",
            "lead_id": lead_id
        }), 201

    except Exception as e:
        print(f"Erro ao registrar lead: {e}")
        traceback.print_exc()
        return jsonify({"error": "Erro ao criar cadastro."}), 500

# --- ENDPOINTS ADMINISTRATIVOS ---

# Estatísticas do sistema
@app.route('/api/admin/stats', methods=['GET'])
@admin_required
def admin_stats():
    """Retorna estatísticas gerais do sistema."""
    db = get_db()
    try:
        stats = {}
        
        # Total de leads
        stats['total_leads'] = db.execute("SELECT COUNT(*) as count FROM leads").fetchone()['count']
        
        # Leads ativos
        stats['active_leads'] = db.execute("SELECT COUNT(*) as count FROM leads WHERE is_active = 1").fetchone()['count']
        
        # Instâncias conectadas
        stats['connected_instances'] = db.execute("SELECT COUNT(*) as count FROM instances WHERE status = 'open'").fetchone()['count']
        
        # Total de planos
        stats['total_plans'] = db.execute("SELECT COUNT(*) as count FROM plans").fetchone()['count']
        
        return jsonify(stats), 200
    except Exception as e:
        print(f"Erro ao buscar estatísticas: {e}")
        return jsonify({"error": "Erro ao buscar estatísticas."}), 500

# Listar todos os leads
@app.route('/api/admin/leads', methods=['GET'])
@admin_required
def admin_list_leads():
    """Lista todos os leads com informações detalhadas."""
    db = get_db()
    try:
        leads = db.execute("""
            SELECT 
                l.id, l.name, l.email, l.phone, l.plan_id, 
                l.plan_expiration_date, l.is_active, l.created_at,
                p.name as plan_name,
                i.instance_name, i.status as instance_status
            FROM leads l
            LEFT JOIN plans p ON l.plan_id = p.id
            LEFT JOIN instances i ON l.id = i.lead_id
            ORDER BY l.created_at DESC
        """).fetchall()
        
        leads_list = []
        for lead in leads:
            leads_list.append({
                'id': lead['id'],
                'name': lead['name'],
                'email': lead['email'],
                'phone': lead['phone'],
                'plan_id': lead['plan_id'],
                'plan_name': lead['plan_name'],
                'plan_expiration_date': lead['plan_expiration_date'],
                'is_active': bool(lead['is_active']),
                'created_at': lead['created_at'],
                'instance_name': lead['instance_name'],
                'instance_status': lead['instance_status']
            })
        
        return jsonify(leads_list), 200
    except Exception as e:
        print(f"Erro ao listar leads: {e}")
        return jsonify({"error": "Erro ao listar leads."}), 500

# Criar novo lead (admin)
@app.route('/api/admin/leads', methods=['POST'])
@admin_required
def admin_create_lead():
    """Cria um novo lead pelo painel admin."""
    data = request.json
    
    required_fields = ['name', 'email', 'password']
    if not all(data.get(field) for field in required_fields):
        return jsonify({"error": "Nome, email e senha são obrigatórios."}), 400
    
    db = get_db()
    try:
        # Verifica se email já existe
        existing = db.execute("SELECT id FROM leads WHERE email = ?", (data['email'],)).fetchone()
        if existing:
            return jsonify({"error": "Email já cadastrado."}), 400
        
        # Insere o lead
        cursor = db.execute("""
            INSERT INTO leads (name, email, phone, password, plan_id, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            data['name'],
            data['email'],
            data.get('phone'),
            data['password'],
            data.get('plan_id'),
            1 if data.get('is_active', True) else 0
        ))
        
        lead_id = cursor.lastrowid
        db.commit()
        
        # NÃO cria mais instância automaticamente
        
        return jsonify({
            "message": "Lead criado com sucesso!",
            "lead_id": lead_id
        }), 201
        
    except Exception as e:
        print(f"Erro ao criar lead: {e}")
        return jsonify({"error": "Erro ao criar lead."}), 500

# Atualizar lead
@app.route('/api/admin/leads/<int:lead_id>', methods=['PUT'])
@admin_required
def admin_update_lead(lead_id):
    """Atualiza informações de um lead."""
    data = request.json
    db = get_db()
    
    try:
        # Verifica se o lead existe
        lead = db.execute("SELECT id FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if not lead:
            return jsonify({"error": "Lead não encontrado."}), 404
        
        # Prepara campos para atualização
        update_fields = []
        params = []
        
        if 'name' in data:
            update_fields.append("name = ?")
            params.append(data['name'])
        
        if 'email' in data:
            # Verifica se o novo email já existe em outro lead
            existing = db.execute("SELECT id FROM leads WHERE email = ? AND id != ?", 
                                (data['email'], lead_id)).fetchone()
            if existing:
                return jsonify({"error": "Email já cadastrado em outro lead."}), 400
            update_fields.append("email = ?")
            params.append(data['email'])
        
        if 'phone' in data:
            update_fields.append("phone = ?")
            params.append(data['phone'])
        
        if 'password' in data and data['password']:
            update_fields.append("password = ?")
            params.append(data['password'])
        
        if 'plan_id' in data:
            update_fields.append("plan_id = ?")
            params.append(data['plan_id'])
        
        if 'is_active' in data:
            update_fields.append("is_active = ?")
            params.append(1 if data['is_active'] else 0)
        
        if update_fields:
            params.append(lead_id)
            query = f"UPDATE leads SET {', '.join(update_fields)} WHERE id = ?"
            db.execute(query, params)
            db.commit()
        
        return jsonify({"message": "Lead atualizado com sucesso!"}), 200
        
    except Exception as e:
        print(f"Erro ao atualizar lead: {e}")
        return jsonify({"error": "Erro ao atualizar lead."}), 500

# Toggle status do lead
@app.route('/api/admin/leads/<int:lead_id>/toggle-status', methods=['POST'])
@admin_required
def admin_toggle_lead_status(lead_id):
    """Ativa ou desativa um lead."""
    data = request.json
    is_active = data.get('is_active', False)
    
    db = get_db()
    try:
        db.execute("UPDATE leads SET is_active = ? WHERE id = ?", 
                  (1 if is_active else 0, lead_id))
        db.commit()
        
        status = "ativado" if is_active else "desativado"
        return jsonify({"message": f"Lead {status} com sucesso!"}), 200
        
    except Exception as e:
        print(f"Erro ao alterar status do lead: {e}")
        return jsonify({"error": "Erro ao alterar status."}), 500

# Deletar lead
@app.route('/api/admin/leads/<int:lead_id>', methods=['DELETE'])
@admin_required
def admin_delete_lead(lead_id):
    """Deleta um lead e suas instâncias associadas."""
    db = get_db()
    try:
        # Deleta instâncias do lead primeiro
        db.execute("DELETE FROM instances WHERE lead_id = ?", (lead_id,))
        
        # Deleta o lead
        db.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        db.commit()
        
        return jsonify({"message": "Lead excluído com sucesso!"}), 200
        
    except Exception as e:
        print(f"Erro ao excluir lead: {e}")
        return jsonify({"error": "Erro ao excluir lead."}), 500

# --- GERENCIAMENTO DE PLANOS ---

# Listar planos
@app.route('/api/admin/plans', methods=['GET'])
@admin_required
def admin_list_plans():
    """Lista todos os planos disponíveis."""
    db = get_db()
    try:
        plans = db.execute("SELECT * FROM plans ORDER BY price").fetchall()
        plans_list = []
        for plan in plans:
            plans_list.append({
                'id': plan['id'],
                'name': plan['name'],
                'description': plan['description'],
                'max_instances': plan['max_instances'],
                'message_limit_per_month': plan['message_limit_per_month'],
                'group_limit': plan['group_limit'],
                'price': plan['price']
            })
        return jsonify(plans_list), 200
    except Exception as e:
        print(f"Erro ao listar planos: {e}")
        return jsonify({"error": "Erro ao listar planos."}), 500

# Criar plano
@app.route('/api/admin/plans', methods=['POST'])
@admin_required
def admin_create_plan():
    """Cria um novo plano."""
    data = request.json
    
    if not data.get('name'):
        return jsonify({"error": "Nome do plano é obrigatório."}), 400
    
    db = get_db()
    try:
        db.execute("""
            INSERT INTO plans (name, description, max_instances, message_limit_per_month, group_limit, price)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            data['name'],
            data.get('description', ''),
            data.get('max_instances', 1),
            data.get('message_limit_per_month', -1),
            data.get('group_limit', -1),
            data.get('price', 0.0)
        ))
        db.commit()
        
        return jsonify({"message": "Plano criado com sucesso!"}), 201
        
    except Exception as e:
        print(f"Erro ao criar plano: {e}")
        return jsonify({"error": "Erro ao criar plano."}), 500

# Inicializa o banco de dados na primeira vez que a aplicação rodar
# A checagem no @app.before_request já faz isso de forma automática.
# Se você remover o @app.before_request, chame init_db() aqui UMA VEZ na inicialização do app.
# init_db() # Descomente esta linha se remover @app.before_request

if __name__ == '__main__':
    # Para rodar localmente:
    # 1. Ative seu ambiente virtual: source venv/bin/activate (ou venv\Scripts\activate no Windows)
    # 2. Defina a variável de ambiente FLASK_APP=app.py (se ainda não fez)
    #    No Windows PowerShell: $env:FLASK_APP="app.py"
    #    No macOS/Linux (Bash/Zsh): export FLASK_APP=app.py
    # 3. Rode o comando: flask run --debug --port 5000
    #
    # Em produção, use um servidor WSGI como Gunicorn ou uWSGI:
    # gunicorn -w 4 app:app -b 0.0.0.0:5000
    print("\n===============================================")
    print(f"!! Rodando Backend Flask em http://127.0.0.1:5000/ !!")
    print("!! Use CTRL+C para parar.                      !!")
    print("!! Banco de dados SQLite em: ./database.db     !!")
    print("===============================================\n")
    # debug=True habilita o reloader e o debugger.
    # use_reloader=False pode ser necessário em alguns ambientes Windows com SQLite para evitar problemas de multi-threading.
    # Em produção, debug=False e use um servidor WSGI.
    app.run(debug=True, port=5000, use_reloader=False)