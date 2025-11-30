from fastapi.responses import StreamingResponse
import io
try:
    from reportlab.pdfgen import canvas
except ImportError:
    canvas = None

import os
from fastapi import FastAPI, HTTPException, Query, Response, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone, date
from dotenv import load_dotenv
import uuid
from pydantic import BaseModel
import paho.mqtt.client as mqtt
import uuid as uuidlib
from time import sleep
import json
from webpay_service import WebPayService
from jobs_client import jobs_auth_client
import requests

# Importar la dependencia de autenticación
from auth import verify_jwt
from email_service import EmailService

# Crear instancia del servicio WebPay y Email
webpay_service = WebPayService()
email_service = EmailService()

# Cargar variables
load_dotenv()

DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT"))
INSTANCE_NAME = os.getenv("CONTAINER_NAME", "fastapi_unknown")

MQTT_BROKER = os.getenv("BROKER")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
REQUESTS_TOPIC = os.getenv("REQUESTS_TOPIC", "properties/requests")
VALIDATION_TOPIC = os.getenv("VALIDATION_TOPIC", "properties/validation")
AUCTIONS_TOPIC = os.getenv("AUCTIONS_TOPIC", "properties/auctions")
GROUP_ID = os.getenv("GROUP_ID", "gX")
ADMIN_GROUP_ID = "6"  # Group ID para reservas del administrador

# Worker service configuration (JobMaster)
# Por defecto :8000 (tu JobMaster corre en 8000). Sobrescribe con WORKER_SERVICE_URL en docker-compose.
WORKER_SERVICE_URL = os.getenv("WORKER_SERVICE_URL", "http://localhost:8000")

FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "https://iic2173-e0-repablo6.me")


class VisitRequestIn(BaseModel):
    url: str

class VisitRequestOut(BaseModel):
    request_id: str
    status: str
    message: str

class MyProperty(BaseModel):
    request_id: str
    url: str
    status: str
    created_at: str
    amount: float
    has_receipt: bool
    property: dict

class PurchaseDetail(BaseModel):
    request_id: str
    url: str
    status: str
    created_at: str
    amount: float
    has_receipt: bool
    property: dict
    rejection_reason: Optional[str] = None
    authorization_code: Optional[str] = None

def mqtt_publish_with_fibonacci(topic: str, payload: str, max_retries: int = 6):
    fib = [1, 1]
    for _ in range(max_retries - 2):
        fib.append(fib[-1] + fib[-2])

    attempt = 0
    while True:
        try:
            client = mqtt.Client()
            if MQTT_USER and MQTT_PASSWORD:
                client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            client.loop_start()
            res = client.publish(topic, payload, qos=1)
            res.wait_for_publish()
            client.loop_stop()
            client.disconnect()
            return True
        except Exception:
            if attempt >= len(fib) - 1:
                return False
            sleep(fib[attempt])
            attempt += 1

def get_connection():
    return psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        cursor_factory=RealDictCursor,
        connect_timeout=10,  # Timeout de conexión de 10 segundos
        application_name="fastapi_app"
    )

def ensure_user_exists(user_id: str, name: str, email: str, phone: str = None):
    """Crear usuario si no existe, NO actualizar si existe"""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
        user = cur.fetchone()
        
        if not user:
            cur.execute(
                "INSERT INTO users (user_id, name, email, phone) VALUES (%s, %s, %s, %s)",
                (user_id, name, email, phone)
            )
            cur.execute(
                "INSERT INTO wallets (user_id, balance) VALUES (%s, 0.00)",
                (user_id,)
            )
            conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def update_user_data(user_id: str, name: str, email: str, phone: str = None):
    """Actualizar datos del usuario existente"""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute(
            "UPDATE users SET name = %s, email = %s, phone = %s, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s",
            (name, email, phone, user_id)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def get_user_balance(user_id: str) -> float:
    """Obtener saldo del usuario"""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("SELECT balance FROM wallets WHERE user_id = %s", (user_id,))
        result = cur.fetchone()
        return float(result['balance']) if result else 0.0
    finally:
        cur.close()
        conn.close()

def update_wallet_balance(user_id: str, new_balance: float):
    """Actualizar saldo del wallet"""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute(
            "UPDATE wallets SET balance = %s, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s",
            (new_balance, user_id)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def create_transaction(user_id: str, transaction_type: str, amount: float, description: str, property_id: str = None) -> str:
    """Crear transacción y retornar ID"""
    transaction_id = f"tx_{uuid.uuid4().hex[:8]}"
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute(
            "INSERT INTO transactions (id, user_id, type, amount, description, property_id) VALUES (%s, %s, %s, %s, %s, %s)",
            (transaction_id, user_id, transaction_type, amount, description, property_id)
        )
        conn.commit()
        return transaction_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def is_admin_user(user_id: str) -> bool:
    """Verificar si un usuario es administrador"""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT is_admin FROM users WHERE user_id = %s", (user_id,))
        result = cur.fetchone()
        return bool(result and result.get("is_admin")) if result else False
    finally:
        cur.close()
        conn.close()

def verify_admin(user: dict = Depends(verify_jwt)) -> dict:
    """Dependencia para verificar que el usuario es administrador"""
    user_id = user.get("sub")
    if not is_admin_user(user_id):
        raise HTTPException(
            status_code=403,
            detail="No tienes permisos de administrador para acceder a este recurso"
        )
    return user


# ===== Helper para encolar recomendaciones en JobMaster =====
def enqueue_recommendations(
    user_id: str,
    property_id: Optional[str] = None,
    prefs: Optional[dict] = None,
    budget_min: Optional[float] = None,
    budget_max: Optional[float] = None,
    location: Optional[str] = None,
    bedrooms: Optional[int] = None,
    bathrooms: Optional[int] = None
) -> Optional[str]:
    """
    Llama al JobMaster para crear un job de recomendaciones.
    Devuelve el job_id o None si falla (no interrumpe el flujo).
    """
    payload = {
        "user_id": user_id,
        "property_id": property_id,
        "preferences": prefs or {},
        "budget_min": budget_min,
        "budget_max": budget_max,
        "location": location,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms
    }
    try:
        r = requests.post(f"{WORKER_SERVICE_URL}/job", json=payload, timeout=6)
        r.raise_for_status()
        data = r.json() if r.content else {}
        return (data or {}).get("job_id")
    except Exception as e:
        print(f"[WARN] enqueue_recommendations failed: {e}")
        return None


app = FastAPI(title="API de Propiedades")

# Configuración de CORS para permitir el frontend
origins = [
    os.getenv("FRONTEND_ORIGIN", "https://iic2173-e0-repablo6.me"),
    "https://www.iic2173-e0-repablo6.me",
    "https://dbdcin4y3ybd.cloudfront.net",
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=86400,
)

# Endpoint adicional para manejar preflight requests
@app.options("/{path:path}")
async def options_handler(path: str):
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Credentials": "true",
        }
    )


# Modelos Pydantic
class UserUpdate(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None

class UserResponse(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    user_id: str
    is_admin: bool = False

class WalletResponse(BaseModel):
    balance: float
    user_id: str

class DepositRequest(BaseModel):
    amount: float

class DepositResponse(BaseModel):
    new_balance: float
    transaction_id: str
    message: str

class PurchaseRequest(BaseModel):
    property_id: str
    amount: float

class PurchaseResponse(BaseModel):
    new_balance: float
    transaction_id: str
    message: str
    job_id: Optional[str] = None   # <-- añadido

class PurchaseErrorResponse(BaseModel):
    error: str
    current_balance: float
    required_amount: float

class TransactionResponse(BaseModel):
    id: str
    type: str
    amount: float
    created_at: str
    description: str

# Modelos para WebPay
class WebPayCreateRequest(BaseModel):
    amount: float
    url: str  # URL de la propiedad para reservar
    description: Optional[str] = "Reserva de visita"

class WebPayCreateResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None

class WebPayCommitRequest(BaseModel):
    token: str
    url: str  # URL de la propiedad para la cual se validó el pago

class WebPayCommitResponse(BaseModel):
    success: bool
    request_id: Optional[str] = None
    message: Optional[str] = None
    transaction: Optional[dict] = None
    error: Optional[str] = None

# Worker service models
class RecommendationRequest(BaseModel):
    property_id: Optional[str] = None
    preferences: Optional[dict] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    location: Optional[str] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None

class RecommendationResponse(BaseModel):
    job_id: str
    status: str
    message: str
    created_at: str

class WorkerHeartbeatResponse(BaseModel):
    status: bool
    timestamp: str
    service: str
    workers_active: int

# Modelos para administrador
class AdminSelection(BaseModel):
    request_id: str
    url: str
    status: str
    created_at: str
    amount: float
    property: dict
    purchased_by_user_id: Optional[str] = None

class AuctionOfferRequest(BaseModel):
    request_id: str  # ID de la reserva del admin que se quiere subastar

class AuctionOfferResponse(BaseModel):
    success: bool
    auction_id: str
    message: str

class AuctionOffer(BaseModel):
    auction_id: str
    proposal_id: str
    url: str
    timestamp: str
    quantity: int
    group_id: int
    operation: str
    property: Optional[dict] = None

class AuctionProposalRequest(BaseModel):
    auction_id: str  # ID de la oferta de otro grupo a la que se responde
    url: str  # URL de la propiedad que se ofrece a cambio
    quantity: int  # Cantidad de visitas que se ofrecen

class AuctionProposalResponse(BaseModel):
    success: bool
    proposal_id: str
    message: str

class AuctionProposalDecisionRequest(BaseModel):
    proposal_id: str  # ID de la propuesta a aceptar/rechazar

class AuctionProposalDecisionResponse(BaseModel):
    success: bool
    message: str

@app.get("/properties")
def list_properties(
    response: Response,
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1),
    price: Optional[float] = None,
    location: Optional[str] = None,
    date: Optional[str] = None
):
    response.headers["X-Instance-Name"] = INSTANCE_NAME

    offset = (page - 1) * limit
    query = """
        SELECT
            p.id,
            p.name,
            p.price,
            p.currency,
            p.bedrooms,
            p.bathrooms,
            p.m2,
            p.location,
            p.img,
            p.url,
            p.is_project,
            p.visit_slots,
            p.timestamp AS last_updated,
            CASE 
                WHEN EXISTS (
                    SELECT 1 FROM purchase_requests pr 
                    WHERE pr.url = p.url 
                    AND pr.is_admin_reservation = TRUE 
                    AND pr.status = 'ACCEPTED'
                    AND pr.purchased_by_user_id IS NULL
                ) THEN TRUE 
                ELSE FALSE 
            END AS is_special_selection
        FROM properties p
        WHERE 1=1
    """
    params = []

    if price is not None:
        query += " AND p.price <= %s"
        params.append(price)
    if location:
        query += " AND LOWER(p.location->>'address') LIKE %s"
        params.append(f"%{location.lower()}%")
    if date:
        try:
            dt = datetime.strptime(date, "%Y-%m-%d")
            query += " AND DATE(p.timestamp) = %s"
            params.append(dt.date())
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato de fecha inválido, usar YYYY-MM-DD")

    query += """
        ORDER BY p.timestamp DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(query, tuple(params))
    results = cur.fetchall()
    cur.close()
    conn.close()
    return results

@app.get("/properties/{property_id}")
def get_property(property_id: int, response: Response, user: dict = Depends(verify_jwt)):
    response.headers["X-Instance-Name"] = INSTANCE_NAME

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM properties WHERE id=%s", (property_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()

    if result is None:
        raise HTTPException(status_code=404, detail="Propiedad no encontrada")
    return result


# ===== ENDPOINTS DE USUARIO =====

@app.get("/me", response_model=UserResponse)
def get_user_profile(user: dict = Depends(verify_jwt)):
    """Obtener datos del usuario loggeado"""
    user_id = user.get("sub")
    name = user.get("name", "")
    NAMESPACE = "https://api.g6.tech/claims"
    email = user.get(f"{NAMESPACE}/email") or user.get("email", "")
    phone = user.get("phone_number", "")
    
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # Verificar si el campo is_admin existe en la tabla
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='users' AND column_name='is_admin'
        """)
        has_is_admin_column = cur.fetchone() is not None
        
        if has_is_admin_column:
            cur.execute(
                "SELECT name, email, phone, is_admin FROM users WHERE user_id = %s",
                (user_id,)
            )
        else:
            # Si no existe el campo, usar consulta sin is_admin y verificar después
            cur.execute(
                "SELECT name, email, phone FROM users WHERE user_id = %s",
                (user_id,)
            )
        
        user_data = cur.fetchone()
        
        if user_data:
            # Asegurar que is_admin sea un boolean
            if has_is_admin_column:
                is_admin_value = user_data.get('is_admin')
                if is_admin_value is None:
                    is_admin_value = False
                else:
                    # Convertir a boolean si viene como string o otro tipo
                    is_admin_value = bool(is_admin_value) if not isinstance(is_admin_value, bool) else is_admin_value
            else:
                # Si no existe el campo, verificar usando la función
                is_admin_value = is_admin_user(user_id)
            
            return UserResponse(
                name=user_data['name'],
                email=user_data['email'],
                phone=user_data['phone'],
                user_id=user_id,
                is_admin=is_admin_value
            )
        else:
            ensure_user_exists(user_id, name, email, phone)
            # Verificar si es admin después de crear el usuario
            is_admin = is_admin_user(user_id)
            return UserResponse(
                name=name,
                email=email,
                phone=phone,
                user_id=user_id,
                is_admin=is_admin
            )
    finally:
        cur.close()
        conn.close()

@app.put("/me", response_model=UserResponse)
def update_user_profile(user_data: UserUpdate, user: dict = Depends(verify_jwt)):
    """Actualizar datos de contacto del usuario"""
    user_id = user.get("sub")
    
    if not user_data.name or not user_data.email:
        raise HTTPException(status_code=400, detail="Nombre y email son requeridos")
    
    name = user.get("name", "")
    NAMESPACE = "https://api.g6.tech/claims"
    email = user.get(f"{NAMESPACE}/email") or user.get("email", "")
    phone = user.get("phone_number", "")
    ensure_user_exists(user_id, name, email, phone)
    
    update_user_data(user_id, user_data.name, user_data.email, user_data.phone)
    
    return UserResponse(
        name=user_data.name,
        email=user_data.email,
        phone=user_data.phone,
        user_id=user_id
    )

# ===== ENDPOINTS DE WALLET =====

@app.get("/wallet", response_model=WalletResponse)
def get_wallet_balance(user: dict = Depends(verify_jwt)):
    """Obtener saldo actual del usuario"""
    user_id = user.get("sub")
    name = user.get("name", "")
    NAMESPACE = "https://api.g6.tech/claims"
    email = user.get(f"{NAMESPACE}/email") or user.get("email", "")
    phone = user.get("phone_number", "")
    
    ensure_user_exists(user_id, name, email, phone)
    
    balance = get_user_balance(user_id)
    
    return WalletResponse(
        balance=balance,
        user_id=user_id
    )

@app.post("/wallet/deposit", response_model=DepositResponse)
def deposit_to_wallet(deposit_data: DepositRequest, user: dict = Depends(verify_jwt)):
    """Cargar dinero al wallet"""
    user_id = user.get("sub")
    name = user.get("name", "")
    NAMESPACE = "https://api.g6.tech/claims"
    email = user.get(f"{NAMESPACE}/email") or user.get("email", "")
    phone = user.get("phone_number", "")
    
    if deposit_data.amount <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0")
    
    ensure_user_exists(user_id, name, email, phone)
    
    current_balance = get_user_balance(user_id)
    new_balance = current_balance + deposit_data.amount
    
    update_wallet_balance(user_id, new_balance)
    
    transaction_id = create_transaction(
        user_id=user_id,
        transaction_type="deposit",
        amount=deposit_data.amount,
        description="Carga de wallet"
    )
    
    return DepositResponse(
        new_balance=new_balance,
        transaction_id=transaction_id,
        message="Depósito exitoso"
    )

@app.get("/wallet/transactions", response_model=list[TransactionResponse])
def get_wallet_transactions(user: dict = Depends(verify_jwt)):
    """Obtener historial de transacciones"""
    user_id = user.get("sub")
    name = user.get("name", "")
    NAMESPACE = "https://api.g6.tech/claims"
    email = user.get(f"{NAMESPACE}/email") or user.get("email", "")
    phone = user.get("phone_number", "")
    
    ensure_user_exists(user_id, name, email, phone)
    
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute(
            "SELECT id, type, amount, description, created_at FROM transactions WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,)
        )
        transactions = cur.fetchall()
        
        return [
            TransactionResponse(
                id=tx['id'],
                type=tx['type'],
                amount=float(tx['amount']),
                created_at=tx['created_at'].isoformat() + "Z",
                description=tx['description']
            )
            for tx in transactions
        ]
    finally:
        cur.close()
        conn.close()

@app.post("/wallet/purchase", response_model=PurchaseResponse)
def purchase_property(purchase_data: PurchaseRequest, user: dict = Depends(verify_jwt)):
    """Procesar compra de propiedad"""
    user_id = user.get("sub")
    name = user.get("name", "")
    NAMESPACE = "https://api.g6.tech/claims"
    email = user.get(f"{NAMESPACE}/email") or user.get("email", "")
    phone = user.get("phone_number", "")
    
    if purchase_data.amount <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0")
    
    ensure_user_exists(user_id, name, email, phone)
    
    current_balance = get_user_balance(user_id)
    
    if current_balance < purchase_data.amount:
        return PurchaseErrorResponse(
            error="Saldo insuficiente",
            current_balance=current_balance,
            required_amount=purchase_data.amount
        )
    
    new_balance = current_balance - purchase_data.amount
    
    update_wallet_balance(user_id, new_balance)
    
    transaction_id = create_transaction(
        user_id=user_id,
        transaction_type="purchase",
        amount=purchase_data.amount,
        description="Compra de propiedad",
        property_id=purchase_data.property_id
    )

    # Disparar recomendaciones (best-effort)
    job_id = None
    try:
        job_id = enqueue_recommendations(
            user_id=user_id,
            property_id=purchase_data.property_id,
            prefs=None
        )
    except Exception as e:
        print(f"[WARN] enqueue_recommendations (purchase) failed: {e}")

    return PurchaseResponse(
        new_balance=new_balance,
        transaction_id=transaction_id,
        message="Compra realizada exitosamente",
        job_id=job_id
    )

@app.api_route("/", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
def root():
    """Endpoint raíz para API Gateway - acepta todos los métodos HTTP"""
    return {
        "message": "API funcionando correctamente",
        "status": "healthy",
        "instance": INSTANCE_NAME,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/health")
def health_check():
    """Endpoint de salud sin autenticación"""
    return {
        "status": "healthy",
        "instance": INSTANCE_NAME,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/health/db")
def health_check_db():
    """Verificar conectividad a la base de datos"""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/auth/test")
def auth_test(user: dict = Depends(verify_jwt)):
    """Endpoint simple para probar autenticación sin BD"""
    NAMESPACE = "https://api.g6.tech/claims"
    email = user.get(f"{NAMESPACE}/email") or user.get("email", "")
    return {
        "status": "authenticated",
        "user_id": user.get("sub"),
        "name": user.get("name"),
        "email": email,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/jobs/test")
def jobs_test(user: dict = Depends(verify_jwt)):
    """Endpoint de prueba que invoca al workers service protegido con access token."""
    result = jobs_auth_client.call_workers_echo({"hello": "world"})
    return result

@app.post("/visits/request", response_model=VisitRequestOut)
def create_visit_request(data: VisitRequestIn, user: dict = Depends(verify_jwt)):
    """
    RF05: Publica una solicitud de compra en properties/requests y registra en BD como PENDING.
    NO descuenta saldo aún; el descuento ocurre solo si llega VALIDATION con ACCEPTED.
    Además: dispara job de recomendaciones (best-effort).
    
    Si el usuario es administrador, usa group_id=6 y marca is_admin_reservation=true.
    """
    user_id = user.get("sub")
    name = user.get("name", "")
    NAMESPACE = "https://api.g6.tech/claims"
    email = user.get(f"{NAMESPACE}/email") or user.get("email", "")
    phone = user.get("phone_number", "")

    ensure_user_exists(user_id, name, email, phone)
    
    # Verificar si es administrador
    admin_user = is_admin_user(user_id)
    effective_group_id = ADMIN_GROUP_ID if admin_user else GROUP_ID

    conn = get_connection(); cur = conn.cursor()
    try:
        # FIX: incluir campos que se usan después (id, bedrooms, bathrooms, location)
        cur.execute("""
            SELECT id, price, currency, visit_slots, bedrooms, bathrooms, location
            FROM properties
            WHERE url = %s
            ORDER BY timestamp DESC
            LIMIT 1
        """, (data.url,))
        prop = cur.fetchone()
        if not prop:
            raise HTTPException(status_code=404, detail="Propiedad no encontrada")

        if prop["visit_slots"] is None or prop["visit_slots"] <= 0:
            raise HTTPException(status_code=409, detail="Sin cupos disponibles")

        request_id = uuidlib.uuid4()
        cur.execute("""
            INSERT INTO purchase_requests (request_id, user_id, group_id, url, origin, operation, status, is_admin_reservation)
            VALUES (%s, %s, %s, %s, %s, %s, 'PENDING', %s)
        """, (str(request_id), user_id, effective_group_id, data.url, 0, "BUY", admin_user))

        cur.execute("UPDATE properties SET visit_slots = visit_slots - 1 WHERE url = %s", (data.url,))

        cur.execute("""
            INSERT INTO event_log (topic, event_type, request_id, url, payload)
            VALUES ('properties/requests', 'REQUEST_SENT', %s, %s, %s::jsonb)
        """, (str(request_id), data.url, json.dumps({
            "request_id": str(request_id),
            "group_id": effective_group_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "url": data.url,
            "origin": 0,
            "operation": "BUY",
            "is_admin_reservation": admin_user
        })))

        conn.commit()
    except:
        conn.rollback()
        raise
    finally:
        cur.close(); conn.close()

    # Publicar al broker (RF05)
    body = json.dumps({
        "request_id": str(request_id),
        "group_id": effective_group_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "url": data.url,
        "origin": 0,
        "operation": "BUY"
    })
    ok = mqtt_publish_with_fibonacci(REQUESTS_TOPIC, body)
    if not ok:
        conn = get_connection(); cur = conn.cursor()
        try:
            cur.execute("UPDATE purchase_requests SET status='ERROR', updated_at=CURRENT_TIMESTAMP WHERE request_id=%s", (str(request_id),))
            cur.execute("UPDATE properties SET visit_slots = visit_slots + 1 WHERE url = %s", (data.url,))
            cur.execute("""
                INSERT INTO event_log (topic, event_type, request_id, url, status, payload)
                VALUES ('properties/requests', 'REQUEST_SEND_ERROR', %s, %s, 'ERROR', %s::jsonb)
            """, (str(request_id), data.url, body))
            conn.commit()
        finally:
            cur.close(); conn.close()
        raise HTTPException(status_code=502, detail="No se pudo publicar la solicitud")
    
    # RF01: Generate recommendations (best-effort)
    try:
        loc_addr = ""
        if prop and isinstance(prop.get("location"), dict):
            loc_addr = prop["location"].get("address", "") or ""
        job_id = enqueue_recommendations(
            user_id=user_id,
            property_id=str(prop["id"]) if prop.get("id") is not None else None,
            prefs={
                "price_range": [
                    float(prop["price"]) * 0.8 if prop.get("price") else None,
                    float(prop["price"]) * 1.2 if prop.get("price") else None
                ],
                "location": loc_addr,
                "bedrooms": prop.get("bedrooms"),
                "bathrooms": prop.get("bathrooms")
            },
            budget_min=float(prop["price"]) * 0.8 if prop.get("price") else None,
            budget_max=float(prop["price"]) * 1.2 if prop.get("price") else None,
            location=loc_addr,
            bedrooms=prop.get("bedrooms"),
            bathrooms=prop.get("bathrooms")
        )
        if job_id:
            conn2 = get_connection(); cur2 = conn2.cursor()
            try:
                cur2.execute("""
                    INSERT INTO event_log (topic, event_type, request_id, url, payload)
                    VALUES ('recommendations', 'RECOMMENDATION_JOB_CREATED', %s, %s, %s::jsonb)
                """, (str(request_id), data.url, json.dumps({
                    "recommendation_job_id": job_id,
                    "user_id": user_id,
                    "property_id": str(prop["id"]) if prop.get("id") else None
                })))
                conn2.commit()
            finally:
                cur2.close(); conn2.close()
    except Exception as e:
        print(f"Failed to create recommendation job: {str(e)}")
    
    return VisitRequestOut(
        request_id=str(request_id),
        status="PENDING",
        message="Solicitud enviada; tu visita quedó en proceso de validación"
    )

# ===== ENDPOINTS DE COMPRAS (PURCHASES) =====

@app.get("/purchases/{purchase_id}", response_model=PurchaseDetail)
def get_purchase_detail(purchase_id: str, user: dict = Depends(verify_jwt)):
    """
    Devuelve el detalle de una compra específica del usuario autenticado.
    """
    user_id = user.get("sub")
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT pr.request_id, pr.url, pr.status, pr.created_at, pr.amount,
                   pr.status = 'ACCEPTED' AS has_receipt,
                   pr.rejection_reason, pr.authorization_code,
                   p.*
            FROM purchase_requests pr
            LEFT JOIN properties p ON pr.url = p.url
            WHERE pr.request_id = %s AND pr.user_id = %s
        """, (purchase_id, user_id))
        
        r = cur.fetchone()
        
        if not r:
            raise HTTPException(status_code=403, detail="No tienes acceso a esta compra o no existe")
        
        property_obj = {k: r[k] for k in r.keys() if k not in ["request_id", "url", "status", "created_at", "amount", "has_receipt", "rejection_reason", "authorization_code"]}
        
        return PurchaseDetail(
            request_id=str(r["request_id"]),
            url=r["url"],
            status=r["status"],
            created_at=r["created_at"].isoformat() + "Z",
            amount=float(r["amount"]) if r["amount"] is not None else 0.0,
            has_receipt=bool(r["has_receipt"]),
            property=property_obj,
            rejection_reason=r.get("rejection_reason"),
            authorization_code=r.get("authorization_code")
        )
    finally:
        cur.close()
        conn.close()

@app.get("/purchases/{purchase_id}/receipt")
def get_purchase_receipt(purchase_id: str, user: dict = Depends(verify_jwt)):
    """
    Entrega el PDF de la boleta de compra si la compra está ACCEPTED.
    Ahora usa AWS Lambda para generar el PDF y lo almacena en S3.
    """
    user_id = user.get("sub")
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT pr.request_id, pr.url, pr.status, pr.created_at, pr.amount,
                   pr.authorization_code, pr.status = 'ACCEPTED' AS has_receipt,
                   p.*, u.name as user_name, u.email as user_email, u.phone as user_phone
            FROM purchase_requests pr
            LEFT JOIN properties p ON pr.url = p.url
            LEFT JOIN users u ON pr.user_id = u.user_id
            WHERE pr.request_id = %s AND pr.user_id = %s
        """, (purchase_id, user_id))
        
        r = cur.fetchone()
        
        if not r:
            raise HTTPException(status_code=403, detail="No tienes acceso a esta compra o no existe")
        
        if not r["has_receipt"]:
            raise HTTPException(status_code=403, detail="La compra aún no está aceptada, no hay boleta disponible")
        
        existing_pdf_url = check_existing_pdf(purchase_id)
        if existing_pdf_url:
            return {"pdf_url": existing_pdf_url, "cached": True}
        
        pdf_url = generate_pdf_with_lambda(r, user)
        
        if pdf_url:
            return {"pdf_url": pdf_url, "cached": False}
        else:
            return generate_pdf_local_fallback(r)
            
    finally:
        cur.close()
        conn.close()

def check_existing_pdf(purchase_id: str) -> Optional[str]:
    """
    Verifica si ya existe un PDF para esta compra en S3
    """
    try:
        import boto3
        s3_client = boto3.client('s3')
        bucket_name = os.getenv('S3_RECEIPTS_BUCKET', 'g6-arquisis-receipts-dev')
        
        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix=f"receipts/boleta_{purchase_id}_"
        )
        
        if 'Contents' in response and response['Contents']:
            latest_file = max(response['Contents'], key=lambda x: x['LastModified'])
            return f"https://{bucket_name}.s3.amazonaws.com/{latest_file['Key']}"
        
        return None
    except Exception as e:
        print(f"Error checking existing PDF: {e}")
        return None

def _convert_decimals(obj):
    """
    Convierte recursivamente todos los Decimal, datetime, date y UUID a tipos serializables JSON
    """
    from decimal import Decimal
    import uuid
    
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat() + 'Z'
    elif isinstance(obj, date):
        return obj.isoformat()
    elif isinstance(obj, uuid.UUID):
        return str(obj)
    elif isinstance(obj, dict):
        return {k: _convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_decimals(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(_convert_decimals(item) for item in obj)
    elif isinstance(obj, set):
        return [_convert_decimals(item) for item in obj]
    elif hasattr(obj, '__dict__'):
        return _convert_decimals(obj.__dict__)
    return obj

def generate_pdf_with_lambda(purchase_data: dict, user_data: dict) -> Optional[str]:
    """
    Genera PDF usando AWS Lambda
    """
    try:
        import boto3
        import json
        from decimal import Decimal
        
        lambda_client = boto3.client('lambda')
        function_name = os.getenv('LAMBDA_PDF_FUNCTION', 'g6-arquisis-pdf-service-dev-generateReceipt')
        
        purchase_data_clean = _convert_decimals(dict(purchase_data))
        
        payload = {
            "purchase_data": {
                "request_id": str(purchase_data_clean['request_id']),
                "amount": purchase_data_clean.get('amount', 0.0),
                "status": purchase_data_clean.get('status', ''),
                "created_at": purchase_data_clean.get('created_at', ''),
                "authorization_code": purchase_data_clean.get('authorization_code')
            },
            "user_data": {
                "name": purchase_data_clean.get('user_name', ''),
                "email": purchase_data_clean.get('user_email', ''),
                "phone": purchase_data_clean.get('user_phone', '')
            },
            "property_data": {
                "name": purchase_data_clean.get('name', ''),
                "price": purchase_data_clean.get('price', 0.0) if purchase_data_clean.get('price') is not None else 0.0,
                "currency": purchase_data_clean.get('currency', 'CLP'),
                "url": purchase_data_clean['url'],
                "location": purchase_data_clean.get('location'),
                "bedrooms": purchase_data_clean.get('bedrooms'),
                "bathrooms": purchase_data_clean.get('bathrooms'),
                "m2": purchase_data_clean.get('m2')
            },
            "group_id": GROUP_ID
        }
        
        payload = _convert_decimals(payload)
        
        def json_serializer(obj):
            from decimal import Decimal
            import uuid
            if isinstance(obj, Decimal):
                return float(obj)
            elif isinstance(obj, datetime):
                return obj.isoformat() + 'Z'
            elif isinstance(obj, date):
                return obj.isoformat()
            elif isinstance(obj, uuid.UUID):
                return str(obj)
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
        
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(payload, default=json_serializer)
        )
        
        result = json.loads(response['Payload'].read())
        
        if result.get('statusCode') == 200:
            body = json.loads(result['body'])
            return body.get('pdf_url')
        else:
            print(f"Lambda error: {result}")
            return None
            
    except Exception as e:
        print(f"Error calling Lambda: {e}")
        return None

def generate_pdf_local_fallback(purchase_data: dict):
    """
    Fallback a generación local de PDF si Lambda falla
    """
    if canvas is None:
        raise HTTPException(status_code=500, detail="reportlab no está instalado y Lambda falló")
    
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.setTitle("Boleta de Compra")
    
    pdf.drawString(100, 800, f"Boleta de Compra - ID: {purchase_data['request_id']}")
    pdf.drawString(100, 780, f"Propiedad: {purchase_data['url']}")
    pdf.drawString(100, 760, f"Monto: ${purchase_data['amount']:.2f}")
    pdf.drawString(100, 740, f"Fecha: {purchase_data['created_at'].isoformat() + 'Z'}")
    pdf.drawString(100, 720, f"Código de Autorización: {purchase_data.get('authorization_code', '-')}")
    pdf.drawString(100, 700, f"Estado: {purchase_data['status']}")
    
    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    
    return StreamingResponse(
        buffer, 
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=boleta_{purchase_data['request_id']}.pdf"}
    )

# Actualizado: Endpoint para historial con información extendida
@app.get("/my-properties", response_model=list[MyProperty])
def my_properties(user: dict = Depends(verify_jwt)):
    """
    Devuelve las solicitudes de compra del usuario con detalles extendidos.
    """
    user_id = user.get("sub")
    NAMESPACE = "https://api.g6.tech/claims"
    email = user.get(f"{NAMESPACE}/email") or user.get("email", "")
    ensure_user_exists(user_id, user.get("name", ""), email, user.get("phone_number", ""))

    conn = get_connection()
    cur = conn.cursor()
    
    print(f"🔍 /my-properties called with user_id={user_id}")
    
    try:
        cur.execute("""
            SELECT pr.request_id, pr.url, pr.status, pr.created_at, pr.amount,
                   pr.status = 'ACCEPTED' AS has_receipt,
                   p.*
            FROM purchase_requests pr
            LEFT JOIN properties p ON pr.url = p.url
            WHERE pr.user_id = %s
            ORDER BY pr.created_at DESC
        """, (user_id,))
        
        rows = cur.fetchall()
        result = []
        
        for r in rows:
            property_obj = {k: r[k] for k in r.keys() if k not in ["request_id", "url", "status", "created_at", "amount", "has_receipt"]}
            result.append(MyProperty(
                request_id=str(r["request_id"]),
                url=r["url"],
                status=r["status"],
                created_at=r["created_at"].isoformat() + "Z",
                amount=float(r["amount"]) if r["amount"] is not None else 0.0,
                has_receipt=bool(r["has_receipt"]),
                property=property_obj
            ))
        
        return result
    finally:
        cur.close()
        conn.close()

# ===== WORKER SERVICE ENDPOINTS =====

@app.post("/webpay/create", response_model=WebPayCreateResponse)
def create_webpay_transaction(
    request: WebPayCreateRequest, 
    user: dict = Depends(verify_jwt)
):
    """Crear transacción de WebPay para validar reserva de visita"""
    user_id = user.get("sub")
    name = user.get("name", "")
    NAMESPACE = "https://api.g6.tech/claims"
    email = user.get(f"{NAMESPACE}/email") or user.get("email", "")
    phone = user.get("phone_number", "")
    
    ensure_user_exists(user_id, name, email, phone)
    
    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0")
    
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT price, visit_slots FROM properties WHERE url = %s", (request.url,))
        prop = cur.fetchone()
        
        if not prop:
            raise HTTPException(status_code=404, detail="Propiedad no encontrada")
        
        if prop["visit_slots"] is None or prop["visit_slots"] <= 0:
            raise HTTPException(status_code=409, detail="Sin cupos disponibles para visita")
        
        expected_amount = float(prop["price"]) * 0.10
        if abs(request.amount - expected_amount) > 0.01:
            raise HTTPException(
                status_code=400, 
                detail=f"El monto debe ser el 10% del precio de la propiedad: ${expected_amount:.2f}"
            )
        
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
    
    order_id = f"order_{uuid.uuid4().hex[:12]}"
    session_id = f"session_{user_id}_{int(datetime.now().timestamp())}"
    return_url = f"{FRONTEND_ORIGIN}/webpay/return?token="
    
    result = webpay_service.create_transaction(
        amount=request.amount,
        order_id=order_id,
        session_id=session_id,
        return_url=return_url
    )
    
    if result["success"]:
        return WebPayCreateResponse(
            success=True,
            token=result["token"],
            url=result["url"]
        )
    else:
        raise HTTPException(status_code=500, detail=result["error"])

@app.post("/webpay/commit", response_model=WebPayCommitResponse)
def commit_webpay_transaction(
    request: WebPayCommitRequest,
    user: dict = Depends(verify_jwt)
):
    """Confirmar transacción de WebPay para reserva de visita"""
    user_id = user.get("sub")
    
    result = webpay_service.commit_transaction(request.token)
    
    if not result["success"]:
        # Error al comunicarse con Transbank
        return WebPayCommitResponse(
            success=False,
            error=result["error"]
        )
    
    transaction_data = result["transaction"]
    response_code = transaction_data.get("response_code", -1)
    amount = float(transaction_data.get("amount", 0))
    authorization_code = transaction_data.get("authorization_code", "")
    transaction_date = transaction_data.get("transaction_date", "")
    
    # Códigos de respuesta de Transbank:
    # 0 = Aprobada, -1 = Rechazada, -2 = Anulada por usuario
    
    if response_code == 0:
        # ✅ TRANSACCIÓN APROBADA
        conn = get_connection()
        cur = conn.cursor()
        try:
            property_url = request.url
            
            cur.execute("SELECT visit_slots FROM properties WHERE url = %s", (property_url,))
            prop = cur.fetchone()
            
            if not prop or prop["visit_slots"] <= 0:
                conn.rollback()
                raise HTTPException(status_code=409, detail="No hay cupos disponibles")
            
            # Verificar si es administrador
            admin_user = is_admin_user(user_id)
            effective_group_id = ADMIN_GROUP_ID if admin_user else GROUP_ID
            
            request_id = uuidlib.uuid4()
            cur.execute("""
                INSERT INTO purchase_requests (request_id, user_id, group_id, url, origin, operation, status, amount, authorization_code, is_admin_reservation)
                VALUES (%s, %s, %s, %s, %s, %s, 'PENDING', %s, %s, %s)
            """, (str(request_id), user_id, effective_group_id, property_url, 0, "BUY", amount, authorization_code, admin_user))
            
            cur.execute("UPDATE properties SET visit_slots = visit_slots - 1 WHERE url = %s", (property_url,))
            
            tx_id = f"tx_{uuid.uuid4().hex[:8]}"
            cur.execute("""
                INSERT INTO transactions (id, user_id, type, amount, description, property_id)
                VALUES (%s, %s, 'purchase', %s, %s, %s)
            """, (tx_id, user_id, amount, f"Reserva validada vía WebPay: {property_url}", property_url))
            
            cur.execute("""
                INSERT INTO event_log (topic, event_type, request_id, url, payload)
                VALUES ('properties/requests', 'WEBPAY_VALIDATED_REQUEST_SENT', %s, %s, %s::jsonb)
            """, (str(request_id), property_url, json.dumps({
                "request_id": str(request_id),
                "group_id": effective_group_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "url": property_url,
                "origin": 0,
                "operation": "BUY",
                "webpay_validated": True,
                "is_admin_reservation": admin_user
            })))
            
            conn.commit()
            
            user_name = user.get("name", "")
            NAMESPACE = "https://api.g6.tech/claims"
            user_email = user.get(f"{NAMESPACE}/email") or user.get("email", "")
            
            if user_email:
                try:
                    email_service.send_payment_confirmation(
                        to_email=user_email,
                        user_name=user_name or "Usuario",
                        request_id=str(request_id),
                        property_url=property_url,
                        amount=amount,
                        authorization_code=authorization_code
                    )
                    print(f"📧 Email de confirmación de pago enviado a {user_email}")
                except Exception as e:
                    print(f"⚠️ Error al enviar email de confirmación: {e}")
            
            body = json.dumps({
                "request_id": str(request_id),
                "group_id": effective_group_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "url": property_url,
                "origin": 0,
                "operation": "BUY"
            })
            
            ok = mqtt_publish_with_fibonacci(REQUESTS_TOPIC, body)
            
            if not ok:
                conn = get_connection()
                cur = conn.cursor()
                cur.execute("UPDATE purchase_requests SET status='ERROR', updated_at=CURRENT_TIMESTAMP WHERE request_id=%s", (str(request_id),))
                cur.execute("UPDATE properties SET visit_slots = visit_slots + 1 WHERE url = %s", (property_url,))
                cur.execute("""
                    INSERT INTO event_log (topic, event_type, request_id, url, status, payload)
                    VALUES ('properties/requests', 'REQUEST_SEND_ERROR', %s, %s, 'ERROR', %s::jsonb)
                """, (str(request_id), property_url, body))
                conn.commit()
                cur.close()
                conn.close()
                raise HTTPException(status_code=502, detail="No se pudo publicar la solicitud")
            
            validation_body = json.dumps({
                "request_id": str(request_id),
                "group_id": effective_group_id,
                "seller": 0,
                "status": "ACCEPTED",
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            validation_ok = mqtt_publish_with_fibonacci(VALIDATION_TOPIC, validation_body)
            if not validation_ok:
                print(f"⚠️ WARNING: No se pudo publicar validación para request_id={request_id}, pero la compra está registrada")
            
            # Disparar recomendaciones post pago validado (best-effort)
            try:
                conn2 = get_connection(); cur2 = conn2.cursor()
                cur2.execute("""
                    SELECT id, price, bedrooms, bathrooms, location
                    FROM properties
                    WHERE url = %s
                    ORDER BY timestamp DESC
                    LIMIT 1
                """, (property_url,))
                p = cur2.fetchone()
                cur2.close(); conn2.close()

                loc_addr = ""
                if p and isinstance(p.get("location"), dict):
                    loc_addr = p["location"].get("address", "") or ""

                _ = enqueue_recommendations(
                    user_id=user_id,
                    property_id=str(p["id"]) if p and p.get("id") is not None else None,
                    prefs={
                        "price_range": [
                            float(p["price"]) * 0.8 if p and p.get("price") else None,
                            float(p["price"]) * 1.2 if p and p.get("price") else None
                        ],
                        "location": loc_addr,
                        "bedrooms": p.get("bedrooms") if p else None,
                        "bathrooms": p.get("bathrooms") if p else None
                    },
                    budget_min=float(p["price"]) * 0.8 if p and p.get("price") else None,
                    budget_max=float(p["price"]) * 1.2 if p and p.get("price") else None,
                    location=loc_addr,
                    bedrooms=p.get("bedrooms") if p else None,
                    bathrooms=p.get("bathrooms") if p else None
                )
            except Exception as e:
                print(f"[WARN] enqueue_recommendations (webpay/commit) failed: {e}")

            return WebPayCommitResponse(
                success=True,
                request_id=str(request_id),
                message="Reserva validada y enviada para procesamiento",
                transaction=transaction_data
            )
            
        except HTTPException:
            conn.rollback()
            raise
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"Error procesando reserva: {str(e)}")
        finally:
            cur.close()
            conn.close()
            
    elif response_code == -2:
        # ❌ ANULADA POR USUARIO
        return WebPayCommitResponse(
            success=False,
            error=f"Transacción anulada por el usuario. Código: {response_code}"
        )
    else:
        # ❌ RECHAZADA (por banco, fondos insuficientes, etc.)
        return WebPayCommitResponse(
            success=False,
            error=f"Transacción rechazada. Código: {response_code}"
        )

@app.get("/webpay/status/{token}")
def get_webpay_status(token: str, user: dict = Depends(verify_jwt)):
    """Obtener estado de transacción WebPay"""
    result = webpay_service.get_transaction_status(token)
    
    if result["success"]:
        return result["transaction"]
    else:
        raise HTTPException(status_code=500, detail=result["error"])

@app.get("/webpay/return")
def webpay_return(token: str = None):
    """Manejar retorno de WebPay"""
    if not token:
        return {"error": "Token no proporcionado"}
    
    result = webpay_service.get_transaction_status(token)
    
    if result["success"]:
        transaction = result["transaction"]
        if transaction["status"] == "AUTHORIZED":
            return {
                "success": True,
                "message": "Pago exitoso",
                "transaction": transaction
            }
        else:
            return {
                "success": False,
                "message": "Pago fallido",
                "transaction": transaction
            }
    else:
        return {
            "success": False,
            "error": result["error"]
        }

@app.post("/recommendations/generate", response_model=RecommendationResponse)
def generate_recommendations(request: RecommendationRequest, user: dict = Depends(verify_jwt)):
    """
    RF01: Generate property recommendations using workers when user purchases a visit
    """
    user_id = user.get("sub")
    try:
        worker_request = {
            "user_id": user_id,
            "property_id": request.property_id,
            "preferences": request.preferences or {},
            "budget_min": request.budget_min,
            "budget_max": request.budget_max,
            "location": request.location,
            "bedrooms": request.bedrooms,
            "bathrooms": request.bathrooms
        }
        response = requests.post(
            f"{WORKER_SERVICE_URL}/job",
            json=worker_request,
            timeout=10
        )
        if response.status_code == 200:
            result = response.json()
            return RecommendationResponse(
                job_id=result["job_id"],
                status=result["status"],
                message=result["message"],
                created_at=result["created_at"]
            )
        else:
            raise HTTPException(
                status_code=502, 
                detail=f"Worker service error: {response.text}"
            )
            
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=503, 
            detail=f"Worker service unavailable: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to generate recommendations: {str(e)}"
        )

@app.get("/recommendations/{job_id}")
def get_recommendation_status(job_id: str, user: dict = Depends(verify_jwt)):
    """
    Get recommendation job status and results
    """
    try:
        response = requests.get(
            f"{WORKER_SERVICE_URL}/job/{job_id}",
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            raise HTTPException(status_code=404, detail="Job not found")
        else:
            raise HTTPException(
                status_code=502, 
                detail=f"Worker service error: {response.text}"
            )
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=503, 
            detail=f"Worker service unavailable: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to get recommendation status: {str(e)}"
        )

# ===== ENDPOINTS DE ADMINISTRADOR =====

@app.get("/admin/selections", response_model=list[AdminSelection])
def get_admin_selections(admin: dict = Depends(verify_admin)):
    """
    Obtener todas las selecciones (reservas) del administrador que aún no han sido compradas por usuarios.
    """
    admin_id = admin.get("sub")
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT pr.request_id, pr.url, pr.status, pr.created_at, pr.amount,
                   pr.purchased_by_user_id,
                   p.*
            FROM purchase_requests pr
            LEFT JOIN properties p ON pr.url = p.url
            WHERE pr.user_id = %s AND pr.is_admin_reservation = TRUE
            ORDER BY pr.created_at DESC
        """, (admin_id,))
        
        rows = cur.fetchall()
        result = []
        
        for r in rows:
            property_obj = {k: r[k] for k in r.keys() if k not in ["request_id", "url", "status", "created_at", "amount", "purchased_by_user_id"]}
            result.append(AdminSelection(
                request_id=str(r["request_id"]),
                url=r["url"],
                status=r["status"],
                created_at=r["created_at"].isoformat() + "Z",
                amount=float(r["amount"]) if r["amount"] is not None else 0.0,
                property=property_obj,
                purchased_by_user_id=r.get("purchased_by_user_id")
            ))
        
        return result
    finally:
        cur.close()
        conn.close()

@app.post("/admin/auctions/offer", response_model=AuctionOfferResponse)
def create_auction_offer(request: AuctionOfferRequest, admin: dict = Depends(verify_admin)):
    """
    Subastar una reserva del administrador para que otros grupos puedan intercambiarla.
    Publica en properties/auctions.
    """
    admin_id = admin.get("sub")
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # Verificar que la reserva existe y pertenece al admin
        cur.execute("""
            SELECT pr.url, pr.status, p.price
            FROM purchase_requests pr
            LEFT JOIN properties p ON pr.url = p.url
            WHERE pr.request_id = %s AND pr.user_id = %s AND pr.is_admin_reservation = TRUE
        """, (request.request_id, admin_id))
        
        reservation = cur.fetchone()
        if not reservation:
            raise HTTPException(status_code=404, detail="Reserva no encontrada o no pertenece al administrador")
        
        if reservation["status"] != "ACCEPTED":
            raise HTTPException(status_code=400, detail="Solo se pueden subastar reservas con estado ACCEPTED")
        
        # Verificar que la reserva no haya sido comprada por un usuario normal
        cur.execute("""
            SELECT purchased_by_user_id
            FROM purchase_requests
            WHERE request_id = %s
        """, (request.request_id,))
        purchase_check = cur.fetchone()
        if purchase_check and purchase_check.get("purchased_by_user_id") is not None:
            raise HTTPException(status_code=400, detail="No se pueden subastar reservas que ya han sido compradas por usuarios")
        
        url = reservation["url"]
        price = float(reservation["price"]) if reservation.get("price") else 0.0
        
        # Generar auction_id
        auction_id = uuidlib.uuid4()
        
        # Crear mensaje para properties/auctions
        auction_body = json.dumps({
            "auction_id": str(auction_id),
            "proposal_id": "",
            "url": url,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "quantity": 1,
            "group_id": int(ADMIN_GROUP_ID),
            "operation": "offer"
        })
        
        # Publicar al broker
        ok = mqtt_publish_with_fibonacci(AUCTIONS_TOPIC, auction_body)
        if not ok:
            raise HTTPException(status_code=502, detail="No se pudo publicar la oferta de subasta")
        
        # Guardar en BD
        cur.execute("""
            INSERT INTO auctions (auction_id, proposal_id, url, timestamp, quantity, group_id, operation, origin_group_id, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active')
        """, (str(auction_id), "", url, datetime.now(timezone.utc), 1, int(ADMIN_GROUP_ID), "offer", GROUP_ID))
        
        conn.commit()
        
        return AuctionOfferResponse(
            success=True,
            auction_id=str(auction_id),
            message="Oferta de subasta publicada exitosamente"
        )
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear oferta de subasta: {str(e)}")
    finally:
        cur.close()
        conn.close()

@app.get("/admin/auctions/offers", response_model=list[AuctionOffer])
def get_auction_offers(admin: dict = Depends(verify_admin)):
    """
    Obtener ofertas de subasta de otros grupos (escuchadas del canal properties/auctions).
    """
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # Obtener ofertas de otros grupos (donde origin_group_id != nuestro GROUP_ID)
        # Solo mostrar ofertas (operation = 'offer'), no propuestas ni otras operaciones
        cur.execute("""
            SELECT a.auction_id, a.proposal_id, a.url, a.timestamp, a.quantity, 
                   a.group_id, a.operation, a.status,
                   p.*
            FROM auctions a
            LEFT JOIN properties p ON a.url = p.url
            WHERE (a.origin_group_id IS NULL OR a.origin_group_id != %s)
            AND a.operation = 'offer'
            AND a.status = 'active'
            ORDER BY a.created_at DESC
        """, (GROUP_ID,))
        
        rows = cur.fetchall()
        result = []
        
        for r in rows:
            try:
                # Construir property_obj solo si hay datos de propiedad
                property_obj = None
                if r.get("id") is not None:
                    property_obj = {k: r[k] for k in r.keys() if k not in ["auction_id", "proposal_id", "url", "timestamp", "quantity", "group_id", "operation", "status"]}
                
                # Validar y convertir timestamp
                timestamp = r.get("timestamp")
                if timestamp is None:
                    timestamp_str = datetime.now(timezone.utc).isoformat() + "Z"
                elif isinstance(timestamp, datetime):
                    timestamp_str = timestamp.isoformat() + "Z"
                else:
                    timestamp_str = str(timestamp)
                
                # Validar group_id
                group_id_val = r.get("group_id")
                if group_id_val is None:
                    group_id_val = 0
                
                # Validar auction_id (puede ser UUID o string)
                auction_id_val = r.get("auction_id")
                if auction_id_val is None:
                    continue  # Saltar si no hay auction_id
                
                # Convertir UUID a string si es necesario
                if hasattr(auction_id_val, '__str__'):
                    auction_id_str = str(auction_id_val)
                else:
                    auction_id_str = str(auction_id_val)
                
                # Validar url (no puede ser None)
                url_val = r.get("url")
                if url_val is None:
                    url_val = ""
                
                result.append(AuctionOffer(
                    auction_id=auction_id_str,
                    proposal_id=r.get("proposal_id") or "",
                    url=str(url_val),
                    timestamp=timestamp_str,
                    quantity=r.get("quantity") or 1,
                    group_id=int(group_id_val),
                    operation=r.get("operation") or "offer",
                    property=property_obj
                ))
            except Exception as e:
                print(f"⚠️ Error procesando fila de oferta: {e}")
                print(f"   Datos: {r}")
                continue  # Continuar con la siguiente fila
        
        return result
    except Exception as e:
        print(f"❌ Error en get_auction_offers: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al obtener ofertas: {str(e)}")
    finally:
        cur.close()
        conn.close()

@app.post("/admin/auctions/propose", response_model=AuctionProposalResponse)
def propose_auction_exchange(request: AuctionProposalRequest, admin: dict = Depends(verify_admin)):
    """
    RF05(1): Proponer un intercambio para las subastas de otros grupos.
    Envía un mensaje de tipo "proposal" por el canal properties/auctions.
    """
    admin_id = admin.get("sub")
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # Verificar que la oferta existe y es de otro grupo
        cur.execute("""
            SELECT a.auction_id, a.url, a.timestamp, a.group_id, a.operation
            FROM auctions a
            WHERE a.auction_id = %s AND a.origin_group_id != %s AND a.operation = 'offer' AND a.status = 'active'
        """, (request.auction_id, GROUP_ID))
        
        auction = cur.fetchone()
        if not auction:
            raise HTTPException(status_code=404, detail="Oferta de subasta no encontrada o no disponible")
        
        # Verificar que tenemos una reserva disponible para la propiedad que ofrecemos
        cur.execute("""
            SELECT pr.request_id, pr.status
            FROM purchase_requests pr
            WHERE pr.url = %s 
            AND pr.user_id = %s 
            AND pr.is_admin_reservation = TRUE 
            AND pr.status = 'ACCEPTED'
            AND pr.purchased_by_user_id IS NULL
            LIMIT 1
        """, (request.url, admin_id))
        
        our_reservation = cur.fetchone()
        if not our_reservation:
            raise HTTPException(
                status_code=400, 
                detail="No tienes una reserva disponible para esta propiedad para ofrecer en intercambio"
            )
        
        if request.quantity <= 0:
            raise HTTPException(status_code=400, detail="La cantidad debe ser mayor a 0")
        
        # Generar proposal_id
        proposal_id = uuidlib.uuid4()
        
        # Obtener timestamp de la propiedad ofrecida
        cur.execute("""
            SELECT timestamp
            FROM properties
            WHERE url = %s
            ORDER BY timestamp DESC
            LIMIT 1
        """, (request.url,))
        prop = cur.fetchone()
        prop_timestamp = prop["timestamp"] if prop else datetime.now(timezone.utc)
        
        # Crear mensaje de propuesta para properties/auctions
        proposal_body = json.dumps({
            "auction_id": request.auction_id,
            "proposal_id": str(proposal_id),
            "url": request.url,
            "timestamp": prop_timestamp.isoformat() + "Z" if isinstance(prop_timestamp, datetime) else prop_timestamp,
            "quantity": request.quantity,
            "group_id": int(ADMIN_GROUP_ID),
            "operation": "proposal"
        })
        
        # Publicar al broker
        ok = mqtt_publish_with_fibonacci(AUCTIONS_TOPIC, proposal_body)
        if not ok:
            raise HTTPException(status_code=502, detail="No se pudo publicar la propuesta de intercambio")
        
        # Guardar en BD
        cur.execute("""
            INSERT INTO auctions (auction_id, proposal_id, url, timestamp, quantity, group_id, operation, origin_group_id, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active')
        """, (
            request.auction_id,
            str(proposal_id),
            request.url,
            prop_timestamp if isinstance(prop_timestamp, datetime) else datetime.now(timezone.utc),
            request.quantity,
            int(ADMIN_GROUP_ID),
            "proposal",
            GROUP_ID
        ))
        
        conn.commit()
        
        return AuctionProposalResponse(
            success=True,
            proposal_id=str(proposal_id),
            message="Propuesta de intercambio enviada exitosamente"
        )
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear propuesta de intercambio: {str(e)}")
    finally:
        cur.close()
        conn.close()

@app.get("/admin/auctions/proposals", response_model=list[AuctionOffer])
def get_auction_proposals(admin: dict = Depends(verify_admin)):
    """
    RF05(2): Obtener propuestas de intercambio recibidas de otros grupos para nuestras subastas.
    """
    admin_id = admin.get("sub")
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # Obtener propuestas (operation = 'proposal') recibidas de otros grupos para nuestras ofertas
        # Las propuestas tienen operation='proposal' y su auction_id corresponde a una oferta nuestra
        # (donde origin_group_id = nuestro GROUP_ID y operation = 'offer')
        cur.execute("""
            SELECT a.auction_id, a.proposal_id, a.url, a.timestamp, a.quantity, 
                   a.group_id, a.operation, a.status,
                   p.*
            FROM auctions a
            LEFT JOIN properties p ON a.url = p.url
            WHERE a.operation = 'proposal' 
            AND a.status = 'active'
            AND a.auction_id IN (
                SELECT auction_id 
                FROM auctions 
                WHERE origin_group_id = %s 
                AND operation = 'offer'
            )
            ORDER BY a.created_at DESC
        """, (GROUP_ID,))
        
        rows = cur.fetchall()
        result = []
        
        for r in rows:
            try:
                # Construir property_obj solo si hay datos de propiedad
                property_obj = None
                if r.get("id") is not None:
                    property_obj = {k: r[k] for k in r.keys() if k not in ["auction_id", "proposal_id", "url", "timestamp", "quantity", "group_id", "operation", "status"]}
                
                # Validar y convertir timestamp
                timestamp = r.get("timestamp")
                if timestamp is None:
                    timestamp_str = datetime.now(timezone.utc).isoformat() + "Z"
                elif isinstance(timestamp, datetime):
                    timestamp_str = timestamp.isoformat() + "Z"
                else:
                    timestamp_str = str(timestamp)
                
                # Validar group_id
                group_id_val = r.get("group_id")
                if group_id_val is None:
                    group_id_val = 0
                
                # Validar auction_id (puede ser UUID o string)
                auction_id_val = r.get("auction_id")
                if auction_id_val is None:
                    continue  # Saltar si no hay auction_id
                
                # Convertir UUID a string si es necesario
                if hasattr(auction_id_val, '__str__'):
                    auction_id_str = str(auction_id_val)
                else:
                    auction_id_str = str(auction_id_val)
                
                # Validar url (no puede ser None)
                url_val = r.get("url")
                if url_val is None:
                    url_val = ""
                
                result.append(AuctionOffer(
                    auction_id=auction_id_str,
                    proposal_id=r.get("proposal_id") or "",
                    url=str(url_val),
                    timestamp=timestamp_str,
                    quantity=r.get("quantity") or 1,
                    group_id=int(group_id_val),
                    operation=r.get("operation") or "proposal",
                    property=property_obj
                ))
            except Exception as e:
                print(f"⚠️ Error procesando fila de propuesta: {e}")
                print(f"   Datos: {r}")
                continue  # Continuar con la siguiente fila
        
        return result
    finally:
        cur.close()
        conn.close()

@app.post("/admin/auctions/proposals/{proposal_id}/accept", response_model=AuctionProposalDecisionResponse)
def accept_auction_proposal(proposal_id: str, admin: dict = Depends(verify_admin)):
    """
    RF05(2): Aceptar una propuesta de intercambio recibida de otro grupo.
    Envía un mensaje de tipo "acceptance" por el canal properties/auctions.
    """
    admin_id = admin.get("sub")
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # Verificar que la propuesta existe y es para una de nuestras ofertas
        cur.execute("""
            SELECT a.auction_id, a.proposal_id, a.url, a.timestamp, a.quantity, a.group_id
            FROM auctions a
            WHERE a.proposal_id = %s 
            AND a.origin_group_id = %s 
            AND a.operation = 'proposal' 
            AND a.status = 'active'
        """, (proposal_id, GROUP_ID))
        
        proposal = cur.fetchone()
        if not proposal:
            raise HTTPException(status_code=404, detail="Propuesta no encontrada o no disponible")
        
        # Usar los campos de la propuesta recibida (url y timestamp de la propuesta que el otro grupo ofreció)
        proposal_url = proposal["url"]
        proposal_timestamp = proposal["timestamp"]
        
        # Crear mensaje de aceptación para properties/auctions
        # Usar los mismos campos de la propuesta que estamos aceptando
        acceptance_body = json.dumps({
            "auction_id": str(proposal["auction_id"]),
            "proposal_id": proposal_id,
            "url": proposal_url,
            "timestamp": proposal_timestamp.isoformat() + "Z" if isinstance(proposal_timestamp, datetime) else proposal_timestamp,
            "quantity": proposal.get("quantity", 1),
            "group_id": int(ADMIN_GROUP_ID),
            "operation": "acceptance"
        })
        
        # Publicar al broker
        ok = mqtt_publish_with_fibonacci(AUCTIONS_TOPIC, acceptance_body)
        if not ok:
            raise HTTPException(status_code=502, detail="No se pudo publicar la aceptación de la propuesta")
        
        # Actualizar estado de la propuesta en BD
        cur.execute("""
            UPDATE auctions 
            SET status = 'accepted', updated_at = CURRENT_TIMESTAMP
            WHERE proposal_id = %s
        """, (proposal_id,))
        
        # También actualizar la oferta original
        cur.execute("""
            UPDATE auctions 
            SET status = 'accepted', updated_at = CURRENT_TIMESTAMP
            WHERE auction_id = %s AND origin_group_id = %s AND operation = 'offer'
        """, (proposal["auction_id"], GROUP_ID))
        
        conn.commit()
        
        return AuctionProposalDecisionResponse(
            success=True,
            message="Propuesta aceptada exitosamente"
        )
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error al aceptar propuesta: {str(e)}")
    finally:
        cur.close()
        conn.close()

@app.post("/admin/auctions/proposals/{proposal_id}/reject", response_model=AuctionProposalDecisionResponse)
def reject_auction_proposal(proposal_id: str, admin: dict = Depends(verify_admin)):
    """
    RF05(2): Rechazar una propuesta de intercambio recibida de otro grupo.
    Envía un mensaje de tipo "rejection" por el canal properties/auctions.
    """
    admin_id = admin.get("sub")
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # Verificar que la propuesta existe y es para una de nuestras ofertas
        cur.execute("""
            SELECT a.auction_id, a.proposal_id, a.url, a.timestamp, a.quantity, a.group_id
            FROM auctions a
            WHERE a.proposal_id = %s 
            AND a.origin_group_id = %s 
            AND a.operation = 'proposal' 
            AND a.status = 'active'
        """, (proposal_id, GROUP_ID))
        
        proposal = cur.fetchone()
        if not proposal:
            raise HTTPException(status_code=404, detail="Propuesta no encontrada o no disponible")
        
        # Usar los campos de la propuesta recibida (url y timestamp de la propuesta que el otro grupo ofreció)
        proposal_url = proposal["url"]
        proposal_timestamp = proposal["timestamp"]
        
        # Crear mensaje de rechazo para properties/auctions
        # Usar los mismos campos de la propuesta que estamos rechazando
        rejection_body = json.dumps({
            "auction_id": str(proposal["auction_id"]),
            "proposal_id": proposal_id,
            "url": proposal_url,
            "timestamp": proposal_timestamp.isoformat() + "Z" if isinstance(proposal_timestamp, datetime) else proposal_timestamp,
            "quantity": proposal.get("quantity", 1),
            "group_id": int(ADMIN_GROUP_ID),
            "operation": "rejection"
        })
        
        # Publicar al broker
        ok = mqtt_publish_with_fibonacci(AUCTIONS_TOPIC, rejection_body)
        if not ok:
            raise HTTPException(status_code=502, detail="No se pudo publicar el rechazo de la propuesta")
        
        # Actualizar estado de la propuesta en BD
        cur.execute("""
            UPDATE auctions 
            SET status = 'rejected', updated_at = CURRENT_TIMESTAMP
            WHERE proposal_id = %s
        """, (proposal_id,))
        
        conn.commit()
        
        return AuctionProposalDecisionResponse(
            success=True,
            message="Propuesta rechazada exitosamente"
        )
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error al rechazar propuesta: {str(e)}")
    finally:
        cur.close()
        conn.close()

@app.post("/visits/purchase-admin-reservation")
def purchase_admin_reservation(data: VisitRequestIn, user: dict = Depends(verify_jwt)):
    """
    Permite a usuarios normales comprar una reserva del administrador con 10% de descuento.
    """
    user_id = user.get("sub")
    name = user.get("name", "")
    NAMESPACE = "https://api.g6.tech/claims"
    email = user.get(f"{NAMESPACE}/email") or user.get("email", "")
    phone = user.get("phone_number", "")
    
    # Verificar que NO es admin
    if is_admin_user(user_id):
        raise HTTPException(status_code=403, detail="Los administradores no pueden comprar reservas de otros administradores")
    
    ensure_user_exists(user_id, name, email, phone)
    
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # Buscar una reserva del admin disponible para esta propiedad
        cur.execute("""
            SELECT pr.request_id, pr.url, pr.status, p.price
            FROM purchase_requests pr
            LEFT JOIN properties p ON pr.url = p.url
            WHERE pr.url = %s 
            AND pr.is_admin_reservation = TRUE 
            AND pr.status = 'ACCEPTED'
            AND pr.purchased_by_user_id IS NULL
            ORDER BY pr.created_at ASC
            LIMIT 1
        """, (data.url,))
        
        admin_reservation = cur.fetchone()
        if not admin_reservation:
            raise HTTPException(status_code=404, detail="No hay reservas del administrador disponibles para esta propiedad")
        
        # Calcular precio con 10% de descuento (el 10% del precio original ya está pagado por el admin)
        # El usuario paga el 10% del precio original (mismo que una reserva normal)
        price = float(admin_reservation["price"]) if admin_reservation.get("price") else 0.0
        amount = price * 0.10
        
        # Verificar saldo del usuario
        cur.execute("SELECT balance FROM wallets WHERE user_id = %s", (user_id,))
        wallet = cur.fetchone()
        balance = float(wallet["balance"]) if wallet else 0.0
        
        if balance < amount:
            raise HTTPException(
                status_code=400,
                detail=f"Saldo insuficiente. Necesitas ${amount:.2f}, tienes ${balance:.2f}"
            )
        
        # Descontar saldo
        new_balance = balance - amount
        cur.execute("UPDATE wallets SET balance = %s, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s", (new_balance, user_id))
        
        # Marcar la reserva como comprada por el usuario
        cur.execute("""
            UPDATE purchase_requests 
            SET purchased_by_user_id = %s, updated_at = CURRENT_TIMESTAMP 
            WHERE request_id = %s
        """, (user_id, admin_reservation["request_id"]))
        
        # Crear transacción
        tx_id = f"tx_{uuid.uuid4().hex[:8]}"
        cur.execute("""
            INSERT INTO transactions (id, user_id, type, amount, description, property_id)
            VALUES (%s, %s, 'purchase', %s, %s, %s)
        """, (tx_id, user_id, amount, f"Compra de reserva del administrador (10% descuento): {data.url}", data.url))
        
        conn.commit()
        
        return {
            "success": True,
            "request_id": str(admin_reservation["request_id"]),
            "message": "Reserva del administrador comprada exitosamente con 10% de descuento",
            "amount_paid": amount,
            "new_balance": new_balance
        }
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error al comprar reserva: {str(e)}")
    finally:
        cur.close()
        conn.close()

@app.get("/worker/heartbeat", response_model=WorkerHeartbeatResponse)
def worker_heartbeat():
    """
    RF04: Check if worker service is available for frontend indicator
    """
    try:
        response = requests.get(
            f"{WORKER_SERVICE_URL}/heartbeat",
            timeout=5
        )
        if response.status_code == 200:
            result = response.json()
            return WorkerHeartbeatResponse(
                status=result["status"],
                timestamp=result["timestamp"],
                service=result["service"],
                workers_active=result["workers_active"]
            )
        else:
            return WorkerHeartbeatResponse(
                status=False,
                timestamp=datetime.now(timezone.utc).isoformat(),
                service="JobMaster",
                workers_active=0
            )
    except requests.exceptions.RequestException:
        return WorkerHeartbeatResponse(
            status=False,
            timestamp=datetime.now(timezone.utc).isoformat(),
            service="JobMaster",
            workers_active=0
        )
    except Exception as e:
        return WorkerHeartbeatResponse(
            status=False,
            timestamp=datetime.now(timezone.utc).isoformat(),
            service="JobMaster",
            workers_active=0
        )

# Alias útil para frontend/proxy
@app.get("/jobs/{job_id}")
def jobs_alias(job_id: str, user: dict = Depends(verify_jwt)):
    return get_recommendation_status(job_id, user)
