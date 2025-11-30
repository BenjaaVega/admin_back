import os
import json
import time
import uuid
from datetime import datetime
import psycopg2
from psycopg2 import OperationalError
from psycopg2.extras import RealDictCursor
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from email_service import EmailService

load_dotenv()

# Inicializar servicio de email
email_service = EmailService()

# --- Broker ---
BROKER = os.getenv("BROKER")
PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")

INFO_TOPIC = os.getenv("INFO_TOPIC", "properties/info")
REQUESTS_TOPIC = os.getenv("REQUESTS_TOPIC", "properties/requests")
VALIDATION_TOPIC = os.getenv("VALIDATION_TOPIC", "properties/validation")
AUCTIONS_TOPIC = os.getenv("AUCTIONS_TOPIC", "properties/auctions")
GROUP_ID = os.getenv("GROUP_ID", "gX")

# --- Postgres ---
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))

# Esperar a que PG esté listo
max_retries = 10
retry_delay = 3
for attempt in range(max_retries):
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
            cursor_factory=RealDictCursor,    # <— importante
        )
        cur = conn.cursor()
        print("✅ Conectado a PostgreSQL!")
        break
    except OperationalError:
        print(f"⚠️ PostgreSQL no listo, reintentando en {retry_delay}s... (Intento {attempt+1}/{max_retries})")
        time.sleep(retry_delay)
else:
    raise Exception("❌ No se pudo conectar a PostgreSQL después de varios intentos")

def extract_number(s):
    if s is None:
        return None
    import re
    m = re.search(r'\d+', str(s))
    return int(m.group()) if m else None

# ---------- Helpers DB ----------
def log_event(cur, topic, event_type, payload, request_id=None, url=None, status=None):
    cur.execute("""
        INSERT INTO event_log (topic, event_type, request_id, url, status, payload)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
    """, (topic, event_type, request_id, url, status, json.dumps(payload)))

def cost_10pct(cur, url):
    cur.execute("SELECT price FROM properties WHERE url=%s ORDER BY timestamp DESC LIMIT 1", (url,))
    row = cur.fetchone()
    return float(row["price"])*0.10 if row and row["price"] is not None else 0.0

# ---------- Handlers ----------
def handle_properties_info(cur, data):
    """UPSERT en properties por URL + log a event_log."""
    url = data.get("url")
    if not url:
        print("⚠️ PROPERTY_INFO sin url; se ignora.")
        return

    name       = data.get("name")
    price      = data.get("price")
    currency   = data.get("currency", "CLP")
    bedrooms   = extract_number(data.get("bedrooms"))
    bathrooms  = extract_number(data.get("bathrooms"))
    m2         = extract_number(data.get("m2"))
    location   = data.get("location")
    img        = data.get("img")
    is_project = bool(data.get("is_project", False))
    ts         = data.get("timestamp")  # ISO 8601 preferido
    initial_slots = data.get("visit_slots", 3)

    # Log del evento
    log_event(cur, INFO_TOPIC, "PROPERTY_INFO", data, url=url)

    # Verificar si la propiedad ya existe
    cur.execute("SELECT visit_slots FROM properties WHERE url = %s", (url,))
    existing_property = cur.fetchone()

    if existing_property:
        # Propiedad duplicada: aumentar visit_slots en 1
        cur.execute("""
            UPDATE properties SET
                name       = %s,
                price      = %s,
                currency   = %s,
                bedrooms   = %s,
                bathrooms  = %s,
                m2         = %s,
                location   = %s::jsonb,
                img        = %s,
                is_project = %s,
                timestamp  = COALESCE(%s, NOW()),
                visit_slots = visit_slots + 1
            WHERE url = %s
        """, (
            name, price, currency, bedrooms, bathrooms, m2,
            json.dumps({"address": location}) if isinstance(location, (str, dict)) else None,
            img, is_project, ts, url
        ))
        print(f"🏠 UPDATE properties (duplicada): {url} - visit_slots aumentado en 1")
    else:
        # Propiedad nueva: insertar con visit_slots iniciales
        cur.execute("""
            INSERT INTO properties
                (name, price, currency, bedrooms, bathrooms, m2, location, img, url, is_project, timestamp, visit_slots)
            VALUES
                (%s,   %s,    %s,       %s,       %s,        %s, %s::jsonb, %s,  %s,  %s,         COALESCE(%s, NOW()), %s)
        """, (
            name, price, currency, bedrooms, bathrooms, m2,
            json.dumps({"address": location}) if isinstance(location, (str, dict)) else None,
            img, url, is_project, ts, initial_slots
        ))
        print(f"🏠 INSERT properties (nueva): {url} - visit_slots inicial: {initial_slots}")

def handle_properties_requests(cur, data):
    req_id = data.get("request_id")
    url    = data.get("url")
    group  = data.get("group_id", "")
    log_event(cur, REQUESTS_TOPIC, "REQUEST_RECEIVED", data, request_id=req_id, url=url, status='OK')

    cur.execute("SELECT 1 FROM purchase_requests WHERE request_id=%s", (req_id,))
    exists = cur.fetchone()

    if exists:
        cur.execute("UPDATE purchase_requests SET status='OK', updated_at=CURRENT_TIMESTAMP WHERE request_id=%s", (req_id,))
    else:
        cur.execute("""
            INSERT INTO purchase_requests (request_id, user_id, group_id, url, origin, operation, status)
            VALUES (%s, NULL, %s, %s, %s, %s, 'OK')
        """, (req_id, group, url, 0, "BUY"))

        cur.execute("""
            UPDATE properties
               SET visit_slots = GREATEST(visit_slots - 1, 0)
             WHERE url = %s
        """, (url,))

def handle_properties_validation(cur, data):
    req_id = data.get("request_id")
    status = data.get("status")
    log_event(cur, VALIDATION_TOPIC, "VALIDATION_RECEIVED", data, request_id=req_id, status=status)

    cur.execute("SELECT url, user_id, is_admin_reservation FROM purchase_requests WHERE request_id=%s", (req_id,))
    pr = cur.fetchone()
    if not pr:
        return
    url = pr["url"]; user_id = pr["user_id"]
    is_admin_reservation = pr.get("is_admin_reservation", False)

    cur.execute("UPDATE purchase_requests SET status=%s, updated_at=CURRENT_TIMESTAMP WHERE request_id=%s", (status, req_id))

    if status == "ACCEPTED":
        # Si es una reserva del admin, NO descontar saldo (el admin ya pagó)
        if not is_admin_reservation and user_id:
            amount = cost_10pct(cur, url)
            cur.execute("SELECT balance FROM wallets WHERE user_id=%s", (user_id,))
            w = cur.fetchone(); balance = float(w["balance"]) if w else 0.0

            if balance < amount:
                print(f"⚠️ Saldo insuficiente para request_id={req_id}. Balance={balance}, Required={amount}")
                cur.execute("UPDATE purchase_requests SET status='ERROR', updated_at=CURRENT_TIMESTAMP WHERE request_id=%s", (req_id,))
                cur.execute("UPDATE properties SET visit_slots = visit_slots + 1 WHERE url = %s", (url,))
                return

            new_balance = balance - amount
            cur.execute("UPDATE wallets SET balance=%s, updated_at=CURRENT_TIMESTAMP WHERE user_id=%s", (new_balance, user_id))

            tx_id = f"tx_{uuid.uuid4().hex[:8]}"
            cur.execute("""
                INSERT INTO transactions (id, user_id, type, amount, description, property_id)
                VALUES (%s, %s, 'purchase', %s, %s, %s)
            """, (tx_id, user_id, amount, "Compra de agendamiento (10%)", url))
            
            # 🆕 ENVIAR EMAIL DE CONFIRMACIÓN DE PAGO ACEPTADO
            cur.execute("SELECT name, email FROM users WHERE user_id=%s", (user_id,))
            user_data = cur.fetchone()
            if user_data and user_data["email"]:
                try:
                    email_service.send_payment_accepted(
                        to_email=user_data["email"],
                        user_name=user_data["name"] or "Usuario",
                        request_id=str(req_id),
                        property_url=url,
                        amount=amount
                    )
                    print(f"📧 Email de pago aceptado enviado a {user_data['email']}")
                except Exception as e:
                    print(f"⚠️ Error al enviar email de pago aceptado: {e}")
    elif str(status).upper() in ("REJECTED","ERROR"):
        cur.execute("UPDATE properties SET visit_slots = visit_slots + 1 WHERE url = %s", (pr["url"],))
        
        # 🆕 ENVIAR EMAIL DE RECHAZO si hay user_id
        if pr["user_id"]:
            cur.execute("SELECT name, email FROM users WHERE user_id=%s", (pr["user_id"],))
            user_data = cur.fetchone()
            if user_data and user_data["email"]:
                try:
                    email_service.send_payment_rejected(
                        to_email=user_data["email"],
                        user_name=user_data["name"] or "Usuario",
                        request_id=str(req_id),
                        property_url=pr["url"],
                        reason=data.get("reason")
                    )
                    print(f"📧 Email de rechazo enviado a {user_data['email']}")
                except Exception as e:
                    print(f"⚠️ Error al enviar email de rechazo: {e}")

def handle_properties_auctions(cur, data):
    """Manejar mensajes de properties/auctions (subastas)"""
    auction_id = data.get("auction_id")
    url = data.get("url")
    group_id = data.get("group_id")
    operation = data.get("operation", "offer")
    
    # Validar campos requeridos
    if not auction_id:
        print(f"⚠️ Mensaje de subasta sin auction_id, se ignora: {data}")
        return
    
    if not url:
        print(f"⚠️ Mensaje de subasta sin url, se ignora: auction_id={auction_id}")
        return
    
    log_event(cur, AUCTIONS_TOPIC, "AUCTION_RECEIVED", data, url=url)
    
    # Extraer el group_id del origen (si viene en el mensaje)
    # Convertir ambos a string para comparación consistente
    origin_group_id = str(group_id) if group_id else str(GROUP_ID)
    our_group_id = str(GROUP_ID)
    
    # Solo guardar ofertas de otros grupos (no las nuestras)
    if origin_group_id != our_group_id:
        # Parsear timestamp
        timestamp_str = data.get("timestamp")
        if timestamp_str:
            try:
                if "Z" in timestamp_str:
                    timestamp_str = timestamp_str.replace("Z", "+00:00")
                timestamp = datetime.fromisoformat(timestamp_str)
            except:
                timestamp = datetime.now()
        else:
            timestamp = datetime.now()
        
        # Verificar si ya existe
        cur.execute("SELECT auction_id FROM auctions WHERE auction_id = %s", (auction_id,))
        exists = cur.fetchone()
        
        if exists:
            cur.execute("""
                UPDATE auctions 
                SET updated_at = CURRENT_TIMESTAMP, status = 'active'
                WHERE auction_id = %s
            """, (auction_id,))
        else:
            cur.execute("""
                INSERT INTO auctions (auction_id, proposal_id, url, timestamp, quantity, group_id, operation, origin_group_id, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active')
            """, (
                auction_id,
                data.get("proposal_id", ""),
                url,
                timestamp,
                data.get("quantity", 1),
                int(group_id) if group_id else 0,
                operation,
                origin_group_id
            ))
        print(f"📦 Oferta de subasta recibida: auction_id={auction_id}, group_id={group_id}, url={url}")

# ---------- MQTT ----------
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ Conectado al broker MQTT!")
        for t in [INFO_TOPIC, REQUESTS_TOPIC, VALIDATION_TOPIC, AUCTIONS_TOPIC]:
            client.subscribe(t)
            print(f"→ Suscrito a {t}")
    else:
        print(f"❌ Error al conectar al broker, código {rc}")

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode('utf-8')
        data = json.loads(payload)
        print(f"📩 [{msg.topic}] {json.dumps(data, indent=2)}")

        if msg.topic == INFO_TOPIC:
            handle_properties_info(cur, data)
        elif msg.topic == REQUESTS_TOPIC:
            handle_properties_requests(cur, data)
        elif msg.topic == VALIDATION_TOPIC:
            handle_properties_validation(cur, data)
        elif msg.topic == AUCTIONS_TOPIC:
            handle_properties_auctions(cur, data)

        conn.commit()
        print("✅ Evento procesado y guardado")
    except Exception as e:
        conn.rollback()
        print(f"⚠️ Error procesando mensaje: {e}")

# --- MQTT client ---
print(f"🔌 MQTT → host={BROKER} port={PORT} user_set={'yes' if MQTT_USER else 'no'}")

client = mqtt.Client(
    protocol=mqtt.MQTTv311,
    callback_api_version=mqtt.CallbackAPIVersion.VERSION1,  # 👈 fuerza API v1 (tu firma actual)
)

if MQTT_USER and MQTT_PASSWORD:
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

client.on_connect = on_connect
client.on_message = on_message

# Conexión asíncrona + loop en background (más estable / logs inmediatos)
client.connect_async(BROKER, PORT, 60)
client.loop_start()

# Mantener vivo el proceso
try:
    while True:
        time.sleep(3600)
except KeyboardInterrupt:
    client.loop_stop()
    client.disconnect()

