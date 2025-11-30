-- Migración: Añadir campos adicionales a purchase_requests
-- Fecha: 2025-10-28
-- Descripción: Añade campos para monto, código de autorización y razón de rechazo

ALTER TABLE purchase_requests 
ADD COLUMN IF NOT EXISTS amount DECIMAL(15,2) DEFAULT 0.00,
ADD COLUMN IF NOT EXISTS authorization_code VARCHAR(255),
ADD COLUMN IF NOT EXISTS rejection_reason TEXT;

-- Comentarios para documentación
COMMENT ON COLUMN purchase_requests.amount IS 'Monto pagado por la reserva/compra';
COMMENT ON COLUMN purchase_requests.authorization_code IS 'Código de autorización de WebPay (solo para transacciones aceptadas)';
COMMENT ON COLUMN purchase_requests.rejection_reason IS 'Razón de rechazo si la solicitud fue rechazada';

