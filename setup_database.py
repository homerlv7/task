#!/usr/bin/env python3
# update_multi_instances_simple.py - Atualiza BD para múltiplas instâncias sem gerenciamento

import sqlite3
import os
from datetime import datetime

def update_database():
    print("🔧 Atualizando banco para suportar múltiplas instâncias...")
    print("=" * 60)
    
    if not os.path.exists('database.db'):
        print("❌ Banco de dados não encontrado!")
        return False
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    try:
        # Verificar estrutura atual
        cursor.execute("PRAGMA table_info(instances)")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Se não tem is_active, precisa atualizar
        if 'is_active' not in columns:
            print("📝 Adicionando coluna is_active às instâncias...")
            cursor.execute("ALTER TABLE instances ADD COLUMN is_active BOOLEAN DEFAULT 1")
            conn.commit()
            print("✅ Coluna is_active adicionada!")
        
        # Remover UNIQUE constraint de instance_name (recriando tabela)
        print("📝 Removendo constraint UNIQUE de instance_name...")
        
        # Backup dos dados
        cursor.execute("SELECT * FROM instances")
        instances_data = cursor.fetchall()
        
        # Recriar tabela sem UNIQUE em instance_name
        cursor.execute("DROP TABLE IF EXISTS instances_new")
        cursor.execute("""
            CREATE TABLE instances_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER,
                instance_name TEXT NOT NULL,
                status TEXT,
                evolution_owner TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                message_count_current_month INTEGER DEFAULT 0,
                last_message_sent_at TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (lead_id) REFERENCES leads(id)
            )
        """)
        
        # Restaurar dados
        if instances_data:
            cursor.executemany("""
                INSERT INTO instances_new (id, lead_id, instance_name, status, evolution_owner,
                                         created_at, last_updated, message_count_current_month,
                                         last_message_sent_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, instances_data)
        
        # Substituir tabela
        cursor.execute("DROP TABLE instances")
        cursor.execute("ALTER TABLE instances_new RENAME TO instances")
        
        # Recriar índices
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_instances_lead_id ON instances (lead_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_instances_instance_name ON instances (instance_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_instances_lead_instance ON instances (lead_id, instance_name)")
        
        conn.commit()
        print("✅ Tabela instances atualizada!")
        
        # Atualizar limites dos planos
        print("📝 Configurando limites de instâncias...")
        
        # Para usuários sem plano (Free) - 1 instância
        cursor.execute("UPDATE plans SET max_instances = 1 WHERE name = 'Free' OR id = 1")
        
        # Para usuários com cadastro - 5 instâncias
        cursor.execute("UPDATE plans SET max_instances = 5 WHERE name != 'Free' AND id != 1")
        
        conn.commit()
        
        # Mostrar configuração
        cursor.execute("SELECT name, max_instances FROM plans")
        plans = cursor.fetchall()
        print("\n📊 Limites configurados:")
        for plan in plans:
            print(f"   {plan[0]}: {plan[1]} instância(s)")
        
        print("\n✅ Banco atualizado com sucesso!")
        return True
        
    except Exception as e:
        print(f"\n❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    update_database()