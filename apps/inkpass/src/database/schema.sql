-- inkPass Database Schema

-- Organizations table
CREATE TABLE IF NOT EXISTS organizations (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    slug VARCHAR UNIQUE NOT NULL,
    settings JSONB DEFAULT '{}',
    plan_id VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_organizations_slug ON organizations(slug);
CREATE INDEX idx_organizations_plan_id ON organizations(plan_id);

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR PRIMARY KEY,
    email VARCHAR UNIQUE NOT NULL,
    password_hash VARCHAR NOT NULL,
    organization_id VARCHAR NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    status VARCHAR DEFAULT 'active',
    two_fa_enabled BOOLEAN DEFAULT FALSE,
    two_fa_secret VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_organization_id ON users(organization_id);
CREATE INDEX idx_users_status ON users(status);

-- Groups table
CREATE TABLE IF NOT EXISTS groups (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    organization_id VARCHAR NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(organization_id, name)
);

CREATE INDEX idx_groups_organization_id ON groups(organization_id);

-- User Groups (many-to-many)
CREATE TABLE IF NOT EXISTS user_groups (
    user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    group_id VARCHAR NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, group_id)
);

CREATE INDEX idx_user_groups_user_id ON user_groups(user_id);
CREATE INDEX idx_user_groups_group_id ON user_groups(group_id);

-- Permissions table
CREATE TABLE IF NOT EXISTS permissions (
    id VARCHAR PRIMARY KEY,
    organization_id VARCHAR NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    resource VARCHAR NOT NULL,
    action VARCHAR NOT NULL,
    conditions JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_permissions_organization_id ON permissions(organization_id);
CREATE INDEX idx_permissions_resource ON permissions(resource);
CREATE INDEX idx_permissions_action ON permissions(action);

-- Group Permissions
CREATE TABLE IF NOT EXISTS group_permissions (
    group_id VARCHAR NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    permission_id VARCHAR NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (group_id, permission_id)
);

CREATE INDEX idx_group_permissions_group_id ON group_permissions(group_id);
CREATE INDEX idx_group_permissions_permission_id ON group_permissions(permission_id);

-- User Permissions (direct user permissions, override group)
CREATE TABLE IF NOT EXISTS user_permissions (
    user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission_id VARCHAR NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, permission_id)
);

CREATE INDEX idx_user_permissions_user_id ON user_permissions(user_id);
CREATE INDEX idx_user_permissions_permission_id ON user_permissions(permission_id);

-- API Keys table
CREATE TABLE IF NOT EXISTS api_keys (
    id VARCHAR PRIMARY KEY,
    organization_id VARCHAR NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id VARCHAR REFERENCES users(id) ON DELETE CASCADE,
    key_hash VARCHAR UNIQUE NOT NULL,
    name VARCHAR NOT NULL,
    scopes JSONB DEFAULT '[]',
    expires_at TIMESTAMP,
    last_used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_api_keys_organization_id ON api_keys(organization_id);
CREATE INDEX idx_api_keys_user_id ON api_keys(user_id);
CREATE INDEX idx_api_keys_key_hash ON api_keys(key_hash);

-- Sessions table
CREATE TABLE IF NOT EXISTS sessions (
    id VARCHAR PRIMARY KEY,
    user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_token_hash ON sessions(token_hash);
CREATE INDEX idx_sessions_expires_at ON sessions(expires_at);

-- OTP Codes table
CREATE TABLE IF NOT EXISTS otp_codes (
    id VARCHAR PRIMARY KEY,
    user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code_hash VARCHAR NOT NULL,
    purpose VARCHAR NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_otp_codes_user_id ON otp_codes(user_id);
CREATE INDEX idx_otp_codes_code_hash ON otp_codes(code_hash);
CREATE INDEX idx_otp_codes_purpose ON otp_codes(purpose);
CREATE INDEX idx_otp_codes_expires_at ON otp_codes(expires_at);

-- Product Plans table
CREATE TABLE IF NOT EXISTS product_plans (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    slug VARCHAR UNIQUE NOT NULL,
    features JSONB DEFAULT '{}',
    limits JSONB DEFAULT '{}',
    price NUMERIC(10, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_product_plans_slug ON product_plans(slug);

-- Organization Plans table
CREATE TABLE IF NOT EXISTS organization_plans (
    organization_id VARCHAR NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    plan_id VARCHAR NOT NULL REFERENCES product_plans(id) ON DELETE CASCADE,
    starts_at TIMESTAMP NOT NULL,
    ends_at TIMESTAMP,
    status VARCHAR DEFAULT 'active',
    PRIMARY KEY (organization_id, plan_id, starts_at)
);

CREATE INDEX idx_organization_plans_organization_id ON organization_plans(organization_id);
CREATE INDEX idx_organization_plans_plan_id ON organization_plans(plan_id);
CREATE INDEX idx_organization_plans_status ON organization_plans(status);


