-- Mimic Notification Service Database Schema

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR PRIMARY KEY,
    email VARCHAR UNIQUE NOT NULL,
    password_hash VARCHAR NOT NULL,
    subscription_tier VARCHAR DEFAULT 'free',
    subscription_expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_email ON users(email);

-- API keys table
CREATE TABLE IF NOT EXISTS api_keys (
    id VARCHAR PRIMARY KEY,
    user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key_hash VARCHAR UNIQUE NOT NULL,
    name VARCHAR NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_api_keys_user_id ON api_keys(user_id);
CREATE INDEX idx_api_keys_key_hash ON api_keys(key_hash);

-- Workflows table
CREATE TABLE IF NOT EXISTS workflows (
    id VARCHAR PRIMARY KEY,
    user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR NOT NULL,
    definition_json JSONB NOT NULL,
    version INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_workflows_user_id ON workflows(user_id);
CREATE INDEX idx_workflows_is_active ON workflows(is_active);

-- Provider keys table (BYOK)
CREATE TABLE IF NOT EXISTS provider_keys (
    id VARCHAR PRIMARY KEY,
    user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider_type VARCHAR NOT NULL,
    encrypted_api_key TEXT,
    encrypted_secret TEXT,
    webhook_url VARCHAR,
    bot_token TEXT,
    from_email VARCHAR,
    from_number VARCHAR,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, provider_type)
);

CREATE INDEX idx_provider_keys_user_id ON provider_keys(user_id);
CREATE INDEX idx_provider_keys_provider_type ON provider_keys(provider_type);
CREATE INDEX idx_provider_keys_is_active ON provider_keys(is_active);

-- Templates table
CREATE TABLE IF NOT EXISTS templates (
    id VARCHAR PRIMARY KEY,
    user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR NOT NULL,
    content TEXT NOT NULL,
    variables JSONB DEFAULT '[]',
    version INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_templates_user_id ON templates(user_id);

-- Delivery logs table
CREATE TABLE IF NOT EXISTS delivery_logs (
    id VARCHAR PRIMARY KEY,
    user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    delivery_id VARCHAR UNIQUE NOT NULL,
    workflow_id VARCHAR REFERENCES workflows(id),
    provider VARCHAR NOT NULL,
    recipient VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    sent_at TIMESTAMP,
    completed_at TIMESTAMP,
    provider_cost NUMERIC(10, 4),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_delivery_logs_user_id ON delivery_logs(user_id);
CREATE INDEX idx_delivery_logs_delivery_id ON delivery_logs(delivery_id);
CREATE INDEX idx_delivery_logs_workflow_id ON delivery_logs(workflow_id);
CREATE INDEX idx_delivery_logs_status ON delivery_logs(status);
CREATE INDEX idx_delivery_logs_created_at ON delivery_logs(created_at);

