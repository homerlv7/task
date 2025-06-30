-- schema.sql - Updated schema for Leads with Password

-- Tabela para armazenar informações dos Planos de Uso
CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL, -- Nome do plano (Ex: Free, Basic, Pro)
    description TEXT, -- Descrição do plano
    max_instances INTEGER NOT NULL DEFAULT 1, -- Máximo de instâncias permitidas por lead neste plano
    message_limit_per_month INTEGER DEFAULT -1, -- Limite de mensagens por mês (-1 para ilimitado)
    group_limit INTEGER DEFAULT -1, -- Limite de grupos que pode buscar/extrair (-1 para ilimitado)
    price REAL DEFAULT 0.0, -- Preço do plano (opcional)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabela para armazenar informações dos Leads/Usuários da sua aplicação
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, -- Nome ou identificador do lead
    email TEXT UNIQUE NOT NULL, -- Email do lead (agora UNIQUE e NOT NULL, usado para login)
    password TEXT NOT NULL, -- Senha do lead (!!! EM PRODUÇÃO, DEVE SER HASHED SECURELY !!!)
    phone TEXT, -- Telefone de contato (opcional)
    plan_id INTEGER, -- ID do plano associado (FOREIGN KEY para a tabela plans)
    plan_expiration_date DATE, -- Data de expiração do plano
    is_active BOOLEAN NOT NULL DEFAULT 1, -- Se o lead está ativo
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP, -- Futuro: rastrear último login
    FOREIGN KEY (plan_id) REFERENCES plans(id) -- Linka com a tabela de planos
);

-- Tabela para armazenar informações das instâncias conectadas
-- Adicionamos a coluna lead_id para vincular a instância a um lead
CREATE TABLE IF NOT EXISTS instances (
    id INTEGER PRIMARY KEY AUTOINCREMENT, -- ID interno do banco de dados
    lead_id INTEGER, -- ID do lead que possui esta instância (FOREIGN KEY para a tabela leads)
    instance_name TEXT UNIQUE NOT NULL, -- O nome da instância na Evolution API (deve ser único GLOBALMENTE por enquanto, ou único por lead)
    status TEXT, -- Último status conhecido (open, close, connecting, qrcode, error, etc.)
    evolution_owner TEXT, -- O número de telefone conectado (pode ser NULL se não conectado)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Quando o registro foi criado no nosso DB
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Quando o status foi atualizado pela última vez
    message_count_current_month INTEGER DEFAULT 0, -- Futuro: contagem de mensagens enviadas no mês atual
    last_message_sent_at TIMESTAMP, -- Futuro: data da última mensagem enviada
    FOREIGN KEY (lead_id) REFERENCES leads(id) -- Linka com a tabela de leads
);

-- Adiciona índices para performance em buscas comuns
CREATE INDEX IF NOT EXISTS idx_instances_lead_id ON instances (lead_id);
CREATE INDEX IF NOT EXISTS idx_instances_instance_name ON instances (instance_name);
CREATE INDEX IF NOT EXISTS idx_leads_plan_id ON leads (plan_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_email_unique ON leads (email); -- Garante email único
-- CREATE INDEX IF NOT EXISTS idx_leads_email ON leads (email); -- Índice na coluna email


-- Tabela para armazenar credenciais de acesso dos leads
CREATE TABLE IF NOT EXISTS credenciais (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    instance_name TEXT UNIQUE NOT NULL,
    lead_id INTEGER NOT NULL,
    tipo TEXT NOT NULL CHECK(tipo IN ('codigo', 'email', 'telefone')),
    -- Campos para tipo 'codigo'
    codigo TEXT,
    pin TEXT,
    -- Campos para tipo 'email' (reutiliza email/senha da tabela leads)
    -- Campos para tipo 'telefone'
    telefone TEXT,
    codigo_verificacao TEXT,
    -- Metadados
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ultimo_acesso TIMESTAMP,
    tentativas_falhas INTEGER DEFAULT 0,
    bloqueado_ate TIMESTAMP,
    status TEXT DEFAULT 'ativo' CHECK(status IN ('ativo', 'bloqueado', 'expirado')),
    FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE,
    FOREIGN KEY (instance_name) REFERENCES instances(instance_name) ON DELETE CASCADE
);

-- Índices para melhor performance
CREATE INDEX IF NOT EXISTS idx_credenciais_codigo ON credenciais (codigo);
CREATE INDEX IF NOT EXISTS idx_credenciais_telefone ON credenciais (telefone);
CREATE INDEX IF NOT EXISTS idx_credenciais_lead_id ON credenciais (lead_id);