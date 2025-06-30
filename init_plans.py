#!/usr/bin/env python3
# init_plans.py - Script para inicializar planos básicos no banco de dados

import sqlite3
import os

def init_plans():
    """Inicializa os planos básicos no banco de dados."""
    
    # Caminho do banco de dados
    db_path = 'database.db'
    
    if not os.path.exists(db_path):
        print(f"Erro: Banco de dados '{db_path}' não encontrado!")
        print("Certifique-se de rodar o Flask pelo menos uma vez para criar o banco.")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Verifica se já existem planos
        existing = cursor.execute("SELECT COUNT(*) FROM plans").fetchone()[0]
        
        if existing == 0:
            # Cria planos básicos
            plans = [
                # (name, description, max_instances, message_limit_per_month, group_limit, price)
                ("Free", "Plano gratuito com recursos limitados", 1, 1000, 5, 0.0),
                ("Basic", "Plano básico para pequenos negócios", 1, 5000, 20, 29.90),
                ("Pro", "Plano profissional com mais recursos", 3, 20000, 100, 79.90),
                ("Enterprise", "Plano empresarial ilimitado", -1, -1, -1, 199.90)
            ]
            
            for plan in plans:
                cursor.execute("""
                    INSERT INTO plans (name, description, max_instances, message_limit_per_month, group_limit, price)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, plan)
            
            conn.commit()
            print(f"✅ {len(plans)} planos iniciais criados com sucesso!")
            print("\nPlanos criados:")
            for plan in plans:
                print(f"  - {plan[0]}: R$ {plan[4]:.2f} - {plan[1]}")
        else:
            print(f"ℹ️  Já existem {existing} planos no banco de dados.")
            
            # Lista os planos existentes
            cursor.execute("SELECT name, price, description FROM plans ORDER BY price")
            existing_plans = cursor.fetchall()
            print("\nPlanos existentes:")
            for plan in existing_plans:
                print(f"  - {plan[0]}: R$ {plan[1]:.2f} - {plan[2]}")
    
    except sqlite3.Error as e:
        print(f"❌ Erro ao inicializar planos: {e}")
    
    finally:
        conn.close()

def create_admin_user():
    """Cria um usuário administrador padrão (opcional)."""
    
    db_path = 'database.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Verifica se já existe um admin
        admin_email = "admin@taskmail.com"
        existing = cursor.execute("SELECT id FROM leads WHERE email = ?", (admin_email,)).fetchone()
        
        if not existing:
            # Cria o usuário admin
            cursor.execute("""
                INSERT INTO leads (name, email, phone, password, plan_id, is_active)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                "Administrador",
                admin_email,
                None,
                "admin123",  # MUDE ISSO EM PRODUÇÃO!
                4,  # Enterprise plan
                1   # Ativo
            ))
            
            lead_id = cursor.lastrowid
            
            # Cria uma instância para o admin
            cursor.execute("""
                INSERT INTO instances (lead_id, instance_name, status)
                VALUES (?, ?, ?)
            """, (lead_id, f"admin_{lead_id}", "disconnected"))
            
            conn.commit()
            print(f"\n✅ Usuário administrador criado!")
            print(f"   Email: {admin_email}")
            print(f"   Senha: admin123 (MUDE ISSO EM PRODUÇÃO!)")
        else:
            print(f"\nℹ️  Usuário administrador já existe ({admin_email})")
    
    except sqlite3.Error as e:
        print(f"❌ Erro ao criar usuário admin: {e}")
    
    finally:
        conn.close()

if __name__ == "__main__":
    print("🚀 Inicializando banco de dados TASK AI...")
    print("=" * 50)
    
    # Inicializa os planos
    init_plans()
    
    # Pergunta se quer criar usuário admin
    print("\n" + "=" * 50)
    response = input("Deseja criar um usuário administrador padrão? (s/n): ").lower()
    if response == 's':
        create_admin_user()
    
    print("\n✅ Inicialização concluída!")
    print("\n⚠️  IMPORTANTE:")
    print("   1. Mude o ADMIN_TOKEN no app.py antes de colocar em produção")
    print("   2. Use senhas seguras e hashing para produção")
    print("   3. Configure HTTPS para proteger as credenciais em trânsito")