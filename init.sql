CREATE TABLE IF NOT EXISTS properties (
    id SERIAL PRIMARY KEY,
    name TEXT,
    price NUMERIC,
    currency TEXT,
    bedrooms INT,
    bathrooms INT,
    m2 NUMERIC,
    location JSONB,
    img TEXT,
    url TEXT,
    is_project BOOLEAN,
    timestamp TIMESTAMP,
    visit_slots INT
);

ALTER TABLE properties
  ADD CONSTRAINT properties_url_key UNIQUE (url);

-- Tabla de usuarios
CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    phone VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de wallets
CREATE TABLE IF NOT EXISTS wallets (
    user_id VARCHAR(255) PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    balance DECIMAL(15,2) DEFAULT 0.00,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de transacciones
CREATE TABLE IF NOT EXISTS transactions (
    id VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    type VARCHAR(20) NOT NULL CHECK (type IN ('deposit', 'purchase')),
    amount DECIMAL(15,2) NOT NULL,
    description TEXT,
    property_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- Índices para mejor rendimiento
CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_created_at ON transactions(created_at);

-- Estado de compra/visita asíncrona
CREATE TYPE request_status AS ENUM ('PENDING','OK','ACCEPTED','REJECTED','ERROR');

-- Solicitudes de compra publicadas/observadas (las nuestras y las de otros grupos)
CREATE TABLE IF NOT EXISTS purchase_requests (
    request_id UUID PRIMARY KEY,
    user_id VARCHAR(255),              -- NULL si es de otro grupo
    group_id TEXT NOT NULL,            -- tu número de grupo (string)
    url TEXT NOT NULL,                 -- URL de la propiedad
    origin INT DEFAULT 0,
    operation TEXT DEFAULT 'BUY',
    status request_status NOT NULL DEFAULT 'PENDING',
    amount DECIMAL(15,2) DEFAULT 0.00, -- Monto pagado por la reserva/compra
    authorization_code VARCHAR(255),   -- Código de autorización de WebPay
    rejection_reason TEXT,             -- Razón de rechazo si fue rechazada
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pr_url ON purchase_requests(url);
CREATE INDEX IF NOT EXISTS idx_pr_status ON purchase_requests(status);
CREATE INDEX IF NOT EXISTS idx_pr_user ON purchase_requests(user_id);

-- Log de eventos (para RF06)
CREATE TABLE IF NOT EXISTS event_log (
    id BIGSERIAL PRIMARY KEY,
    topic TEXT NOT NULL,               -- properties/info | properties/requests | properties/validation
    event_type TEXT NOT NULL,          -- e.g., PROPERTY_INFO, REQUEST_SENT, REQUEST_RECEIVED, VALIDATION_RECEIVED
    request_id UUID,
    url TEXT,
    status request_status,
    payload JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_event_req ON event_log(request_id);
CREATE INDEX IF NOT EXISTS idx_event_topic ON event_log(topic);
