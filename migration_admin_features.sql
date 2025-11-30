-- Migración para agregar funcionalidades de administrador

-- Agregar campo is_admin a la tabla users
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;

-- Agregar campo is_admin_reservation a purchase_requests para identificar reservas del admin
ALTER TABLE purchase_requests ADD COLUMN IF NOT EXISTS is_admin_reservation BOOLEAN DEFAULT FALSE;

-- Agregar campo purchased_by_user_id para rastrear si una reserva del admin fue comprada por un usuario
ALTER TABLE purchase_requests ADD COLUMN IF NOT EXISTS purchased_by_user_id VARCHAR(255);

-- Crear tabla para almacenar subastas (ofertas recibidas y enviadas)
CREATE TABLE IF NOT EXISTS auctions (
    auction_id UUID PRIMARY KEY,
    proposal_id TEXT DEFAULT '',
    url TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    quantity INT DEFAULT 1,
    group_id INT NOT NULL,
    operation TEXT DEFAULT 'offer',
    origin_group_id TEXT,  -- Grupo que envía la oferta (nuestro grupo)
    status TEXT DEFAULT 'active',  -- active, accepted, rejected, expired
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_auctions_url ON auctions(url);
CREATE INDEX IF NOT EXISTS idx_auctions_group_id ON auctions(group_id);
CREATE INDEX IF NOT EXISTS idx_auctions_status ON auctions(status);
CREATE INDEX IF NOT EXISTS idx_auctions_origin_group ON auctions(origin_group_id);

-- Índice para búsquedas de reservas del admin
CREATE INDEX IF NOT EXISTS idx_pr_admin_reservation ON purchase_requests(is_admin_reservation);
CREATE INDEX IF NOT EXISTS idx_pr_purchased_by ON purchase_requests(purchased_by_user_id);

