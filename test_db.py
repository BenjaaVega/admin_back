import os
import psycopg2
from dotenv import load_dotenv
load_dotenv()

DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")

conn = psycopg2.connect(
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT
)

try:
    # Establecer conexión
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT
    )
    print("✅ Conexión exitosa!")

    cur = conn.cursor()

    # Probar lectura del sistema
    cur.execute("SELECT version();")
    print("Versión PostgreSQL:", cur.fetchone()[0])

    # Inserción de prueba
    insert_query = """
        INSERT INTO properties (
            name, price, currency, bedrooms, bathrooms, m2, 
            location, img, url, is_project, timestamp, visit_slots
        ) VALUES (
            'TEST PROPERTY', 1000.0, 'UF', '1', '1', '45', 
            'Maipu', 'http://img', 'http://url', false, NOW(), 1
        );
    """
    cur.execute(insert_query)
    conn.commit()

    # Leer los registros
    cur.execute("SELECT id, name, price FROM properties;")
    rows = cur.fetchall()
    print("📄 Registros actuales en tabla properties:")
    for row in rows:
        print(row)

    cur.close()
    conn.close()

except Exception as e:
    print("❌ Error:", e)