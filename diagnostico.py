#!/usr/bin/env python3
# diagnostico.py - Script de diagnóstico completo do sistema TASK AI

import os
import sqlite3
import requests
import json
from datetime import datetime

# Cores para output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

def print_header(title):
    print(f"\n{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BLUE}{title.center(60)}{Colors.END}")
    print(f"{Colors.BLUE}{'='*60}{Colors.END}\n")

def print_success(msg):
    print(f"{Colors.GREEN}✓ {msg}{Colors.END}")

def print_error(msg):
    print(f"{Colors.RED}✗ {msg}{Colors.END}")

def print_warning(msg):
    print(f"{Colors.YELLOW}⚠ {msg}{Colors.END}")

def print_info(msg):
    print(f"{Colors.BLUE}ℹ {msg}{Colors.END}")

# 1. Verificar arquivos necessários
def check_files():
    print_header("1. VERIFICANDO ARQUIVOS")
    
    required_files = {
        'app.py': 'Backend Flask',
        'schema.sql': 'Schema do banco de dados',
        '.env': 'Variáveis de ambiente',
        'database.db': 'Banco de dados SQLite'
    }
    
    all_ok = True
    for file, desc in required_files.items():
        if os.path.exists(file):
            size = os.path.getsize(file)
            print_success(f"{file} encontrado ({desc}) - {size} bytes")
        else:
            if file == 'database.db':
                print_warning(f"{file} não encontrado (será criado ao rodar o Flask)")
            else:
                print_error(f"{file} NÃO encontrado ({desc})")
                all_ok = False
    
    return all_ok

# 2. Verificar variáveis de ambiente
def check_env():
    print_header("2. VERIFICANDO VARIÁVEIS DE AMBIENTE")
    
    if os.path.exists('.env'):
        with open('.env', 'r') as f:
            content = f.read()
            
        has_evolution_url = 'EVOLUTION_API_URL' in content
        has_api_key = 'GLOBAL_API_KEY' in content
        
        if has_evolution_url:
            print_success("EVOLUTION_API_URL encontrada no .env")
        else:
            print_error("EVOLUTION_API_URL NÃO encontrada no .env")
            
        if has_api_key:
            print_success("GLOBAL_API_KEY encontrada no .env")
        else:
            print_error("GLOBAL_API_KEY NÃO encontrada no .env")
            
        return has_evolution_url and has_api_key
    else:
        print_error("Arquivo .env não encontrado!")
        print_info("Crie um arquivo .env com:")
        print("EVOLUTION_API_URL=http://localhost:8080")
        print("GLOBAL_API_KEY=sua_chave_aqui")
        return False

# 3. Verificar banco de dados
def check_database():
    print_header("3. VERIFICANDO BANCO DE DADOS")
    
    if not os.path.exists('database.db'):
        print_warning("Banco de dados não existe ainda")
        return False
    
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        # Verificar tabelas
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        table_names = [t[0] for t in tables]
        
        required_tables = ['plans', 'leads', 'instances']
        all_tables_ok = True
        
        for table in required_tables:
            if table in table_names:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print_success(f"Tabela '{table}' existe com {count} registros")
            else:
                print_error(f"Tabela '{table}' NÃO existe")
                all_tables_ok = False
        
        # Verificar planos especificamente
        if 'plans' in table_names:
            cursor.execute("SELECT id, name, price FROM plans ORDER BY id")
            plans = cursor.fetchall()
            if plans:
                print_info("\nPlanos cadastrados:")
                for plan in plans:
                    print(f"  ID: {plan[0]} | Nome: {plan[1]} | Preço: R$ {plan[2]}")
            else:
                print_warning("\nNenhum plano cadastrado! Execute: python init_plans.py")
        
        conn.close()
        return all_tables_ok
        
    except Exception as e:
        print_error(f"Erro ao acessar banco de dados: {e}")
        return False

# 4. Verificar se o Flask está rodando
def check_flask():
    print_header("4. VERIFICANDO BACKEND FLASK")
    
    base_url = "http://127.0.0.1:5000"
    
    try:
        response = requests.get(f"{base_url}/", timeout=2)
        if response.status_code == 200:
            print_success(f"Backend Flask está ONLINE em {base_url}")
            print_info(f"Resposta: {response.text[:50]}...")
            return True
        else:
            print_error(f"Backend retornou status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print_error("Backend Flask NÃO está rodando!")
        print_info("Execute em outro terminal: python app.py")
        return False
    except Exception as e:
        print_error(f"Erro ao conectar no backend: {e}")
        return False

# 5. Testar endpoints principais
def test_endpoints():
    print_header("5. TESTANDO ENDPOINTS")
    
    base_url = "http://127.0.0.1:5000"
    admin_token = "SEU_TOKEN_ADMIN_SUPER_SECRETO_AQUI_12345"
    
    endpoints_to_test = [
        {
            'name': 'Listar Planos (Admin)',
            'method': 'GET',
            'url': f'{base_url}/api/admin/plans',
            'headers': {'X-Admin-Token': admin_token}
        },
        {
            'name': 'Listar Leads (Admin)',
            'method': 'GET',
            'url': f'{base_url}/api/admin/leads',
            'headers': {'X-Admin-Token': admin_token}
        },
        {
            'name': 'Estatísticas (Admin)',
            'method': 'GET',
            'url': f'{base_url}/api/admin/stats',
            'headers': {'X-Admin-Token': admin_token}
        }
    ]
    
    all_ok = True
    for endpoint in endpoints_to_test:
        try:
            if endpoint['method'] == 'GET':
                response = requests.get(
                    endpoint['url'], 
                    headers=endpoint.get('headers', {}),
                    timeout=2
                )
            
            if response.status_code == 200:
                data = response.json()
                print_success(f"{endpoint['name']}: OK")
                if isinstance(data, list):
                    print_info(f"  Retornou {len(data)} itens")
                elif isinstance(data, dict):
                    print_info(f"  Retornou: {list(data.keys())}")
            else:
                print_error(f"{endpoint['name']}: Status {response.status_code}")
                print_info(f"  Resposta: {response.text[:100]}...")
                all_ok = False
                
        except Exception as e:
            print_error(f"{endpoint['name']}: {str(e)}")
            all_ok = False
    
    return all_ok

# 6. Criar usuário de teste
def create_test_user():
    print_header("6. CRIANDO USUÁRIO DE TESTE")
    
    base_url = "http://127.0.0.1:5000"
    
    test_user = {
        "name": "Usuário Teste",
        "email": f"teste_{datetime.now().timestamp():.0f}@example.com",
        "phone": "(11) 98765-4321",
        "password": "senha123"
    }
    
    try:
        response = requests.post(
            f"{base_url}/api/lead/register",
            json=test_user,
            headers={'Content-Type': 'application/json'},
            timeout=5
        )
        
        if response.status_code == 201:
            print_success("Usuário de teste criado com sucesso!")
            print_info(f"  Email: {test_user['email']}")
            print_info(f"  Senha: {test_user['password']}")
            return test_user
        else:
            print_error(f"Falha ao criar usuário: {response.status_code}")
            print_info(f"  Resposta: {response.text}")
            return None
            
    except Exception as e:
        print_error(f"Erro ao criar usuário: {e}")
        return None

# 7. Sugestões de correção
def show_fixes():
    print_header("RESUMO E CORREÇÕES SUGERIDAS")
    
    print_info("Se algum teste falhou, siga estas etapas:")
    print("\n1. RESETAR O BANCO DE DADOS:")
    print("   rm database.db")
    print("   python app.py  # Em um terminal")
    print("   python init_plans.py  # Em outro terminal")
    
    print("\n2. VERIFICAR ARQUIVO .env:")
    print("   Certifique-se de ter:")
    print("   EVOLUTION_API_URL=http://localhost:8080")
    print("   GLOBAL_API_KEY=sua_chave_aqui")
    
    print("\n3. TESTAR MANUALMENTE:")
    print("   - Abra http://localhost:5000/ no navegador")
    print("   - Deve aparecer: 'Backend TASK AI rodando!'")
    
    print("\n4. ORDEM DE ACESSO:")
    print("   1. http://localhost:5000/lead_register.html")
    print("   2. http://localhost:5000/admin_panel.html (ativar o lead)")
    print("   3. http://localhost:5000/lead_login.html")

# Executar todos os testes
def main():
    print_header("DIAGNÓSTICO COMPLETO - TASK AI")
    print(f"Data/Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    
    # Executar verificações
    files_ok = check_files()
    env_ok = check_env()
    db_ok = check_database()
    flask_ok = check_flask()
    
    if flask_ok:
        endpoints_ok = test_endpoints()
        if endpoints_ok and db_ok:
            user = create_test_user()
    
    # Mostrar sugestões
    show_fixes()
    
    print_header("FIM DO DIAGNÓSTICO")

if __name__ == "__main__":
    main()