from celery import shared_task
import psycopg2
from psycopg2.extras import RealDictCursor
import os, time, math, json
from dotenv import load_dotenv

load_dotenv()

DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = int(os.getenv("DB_PORT", "5432"))

# ---------- DB ----------
def get_connection():
    return psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        cursor_factory=RealDictCursor,
        connect_timeout=10
    )

# ---------- Helpers de location ---------
def _coerce_json(obj):
    """Si viene string JSON -> dict; si ya es dict, lo retorna."""
    if isinstance(obj, dict):
        return obj
    if obj is None:
        return {}
    # puede venir como str (a veces serializado)
    try:
        return json.loads(obj)
    except Exception:
        return {}

def _get_address(loc):
    """Extrae address desde location JSON."""
    loc = _coerce_json(loc)
    addr = loc.get("address")
    if isinstance(addr, str):
        return addr.strip()
    return ""

def _extract_comuna_key(address: str) -> str:
    """
    Heurística simple: toma el último segmento después de la última coma.
    E.g. "Los Tres Antonios 300, Ñuñoa, Metro Ñuñoa, Ñuñoa" -> "ñuñoa"
    """
    if not address:
        return ""
    parts = [p.strip().lower() for p in address.split(",") if p.strip()]
    return parts[-1] if parts else address.strip().lower()

def _get_lat_lon(loc):
    """
    Busca lat/lon dentro del JSON (claves comunes).
    - {'lat': ..., 'lon': ...} o {'latitude': ..., 'longitude': ...}
    - GeoJSON: {'coordinates': [lon, lat]} (aceptamos numéricos)
    Retorna (lat, lon) o (None, None)
    """
    loc = _coerce_json(loc)
    lat = None
    lon = None

    # 1) lat/lon directos
    for k_lat, k_lon in (("lat", "lon"), ("latitude", "longitude")):
        if k_lat in loc and k_lon in loc:
            try:
                lat = float(loc[k_lat]) if loc[k_lat] is not None else None
                lon = float(loc[k_lon]) if loc[k_lon] is not None else None
                if lat is not None and lon is not None:
                    return lat, lon
            except Exception:
                pass

    # 2) GeoJSON coordinates
    coords = loc.get("coordinates")
    if isinstance(coords, (list, tuple)) and len(coords) >= 2:
        try:
            # GeoJSON es [lon, lat]
            lon = float(coords[0])
            lat = float(coords[1])
            return lat, lon
        except Exception:
            pass

    return None, None

def _haversine(lat1, lon1, lat2, lon2):
    """Distancia en metros entre dos puntos (lat, lon) usando Haversine."""
    if None in (lat1, lon1, lat2, lon2):
        return None
    R = 6371000.0
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (math.sin(dphi/2)**2 +
         math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlmb/2)**2)
    return 2 * R * math.asin(math.sqrt(a))

# ---------- Algoritmo simple del enunciado ----------
@shared_task(name="tasks.generate_recommendations_simple", bind=True, time_limit=60, soft_time_limit=45)
def generate_recommendations_simple(self, property_id: int):
    """
    Enunciado E2 (adaptado a tu esquema):
    1) Obtener dirección (para "comuna" aproximada), dormitorios y precio de la propiedad base.
       *lat/lon* se obtienen desde location JSON si existen.
    2) Filtrar: mismo nº de dormitorios, precio <= base, y misma "comuna" (por clave derivada del address).
    3) Ordenar por distancia geográfica (si hay coords, Haversine) y luego por precio.
    4) Retornar top 3.
    """
    t0 = time.perf_counter()
    self.update_state(state="PROGRESS", meta={"progress": 5})

    conn = get_connection()
    cur = conn.cursor()
    try:
        # Paso 1: propiedad base (usa tu esquema real)
        cur.execute("""
            SELECT id, name, price, bedrooms, bathrooms, m2, url, location, timestamp
            FROM properties
            WHERE id = %s
            ORDER BY timestamp DESC
            LIMIT 1
        """, (property_id,))
        base = cur.fetchone()
        if not base:
            return {"recommendations": [], "total_found": 0, "reason": "base_property_not_found"}

        base_addr = _get_address(base.get("location"))
        base_comuna_key = _extract_comuna_key(base_addr)
        base_lat, base_lon = _get_lat_lon(base.get("location"))

        self.update_state(state="PROGRESS", meta={"progress": 20})

        # Paso 2: candidatos (filtramos en SQL por price/bedrooms; "comuna" se filtra en Python por address)
        # Limit para no traer TODO si la tabla es grande
        cur.execute("""
            SELECT id, name, price, bedrooms, bathrooms, m2, url, location, timestamp
            FROM properties
            WHERE bedrooms = %s
              AND price <= %s
              AND id <> %s
            ORDER BY timestamp DESC
            LIMIT 1000
        """, (base["bedrooms"], base["price"], base["id"]))
        rows = cur.fetchall()

        # Filtrado por "comuna" aproximada
        candidates = []
        for r in rows:
            addr = _get_address(r.get("location"))
            if _extract_comuna_key(addr) == base_comuna_key:
                candidates.append(r)

        self.update_state(state="PROGRESS", meta={"progress": 60})

        # Paso 3: ordenar por distancia y precio
        def _sort_key(r):
            lat, lon = _get_lat_lon(r.get("location"))
            dist = _haversine(base_lat, base_lon, lat, lon) if (base_lat is not None and base_lon is not None) else None
            # si no hay coords, distancia = inf para que mande precio
            d = dist if dist is not None else float("inf")
            price_val = float(r["price"]) if r["price"] is not None else 1e18
            return (d, price_val)

        top = sorted(candidates, key=_sort_key)[:3]

        # Paso 4: salida
        out = []
        for r in top:
            lat, lon = _get_lat_lon(r.get("location"))
            dist = _haversine(base_lat, base_lon, lat, lon) if (base_lat is not None and base_lon is not None and lat is not None and lon is not None) else None
            out.append({
                "property_id": str(r["id"]),
                "name": r["name"],
                "price": float(r["price"]) if r["price"] is not None else None,
                "bedrooms": int(r["bedrooms"]) if r["bedrooms"] is not None else None,
                "bathrooms": int(r["bathrooms"]) if r["bathrooms"] is not None else None,
                "m2": float(r["m2"]) if r["m2"] is not None else None,
                "url": r.get("url"),
                "location_address": _get_address(r.get("location")),
                "distance_meters": round(dist, 2) if dist is not None else None
            })

        dt = time.perf_counter() - t0
        self.update_state(state="PROGRESS", meta={"progress": 100})

        return {
            "recommendations": out,
            "total_found": len(out),
            "base_property_id": property_id,
            "reason": "success" if out else "no_matches_found",
            "processing_time": f"{dt:.2f}s",
            "algorithm": "enunciado_e2_simple_filter"
        }

    finally:
        cur.close()
        conn.close()

# ---------- Wrapper compatible con tu JobMaster ----------
@shared_task(name="tasks.generate_recommendations", bind=True, time_limit=90, soft_time_limit=60)
def generate_recommendations(self, job_id: str, user_id: str, preferences: dict):
    """
    Compatibilidad con el JobMaster que llama:
      send_task('tasks.generate_recommendations', args=[job_id, user_id, preferences])
    Aquí esperamos que 'property_id' venga en 'preferences' o, al menos, que el JobMaster nos lo pase.
    """
    property_id = None
    try:
        if isinstance(preferences, dict):
            # acepta 'property_id' como str o int
            pid = preferences.get("property_id")
            if pid is None:
                # algunos JobMaster envían 'property_id' a nivel raíz del job_data;
                # si hiciste cambios para incluirlo en 'preferences', cae aquí;
                # si no, puedes ajustar el JobMaster o setear un valor por defecto.
                return {
                    "recommendations": [],
                    "total_found": 0,
                    "error": "property_id is required in preferences",
                    "job_id": job_id,
                    "user_id": user_id
                }
            property_id = int(pid)
        else:
            return {
                "recommendations": [],
                "total_found": 0,
                "error": "invalid preferences payload",
                "job_id": job_id,
                "user_id": user_id
            }

        # delega al algoritmo simple
        res = generate_recommendations_simple(property_id)
        # Si es AsyncResult, obtén el resultado:
        if hasattr(res, "get"):  # por si Celery lo envolviera, normalmente no aquí
            res = res.get(timeout=60)

        # adjunta metadata del job
        if isinstance(res, dict):
            res.update({"job_id": job_id, "user_id": user_id})
        return res

    except Exception as e:
        raise self.retry(exc=e, countdown=30, max_retries=3)
