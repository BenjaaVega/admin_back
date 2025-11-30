#!/usr/bin/env python3
"""
Script simple para crear un usuario administrador.
Uso: python create_admin_user.py <user_id> [name] [email]
"""

import sys
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))

def create_admin_user(user_id: str, name: str = "Administrador", email: str = "admin@example.com"):
    """Crear o actualizar usuario como administrador"""
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
            cursor_factory=RealDictCursor
        )
        cur = conn.cursor()
        
        # Verificar si el usuario existe
        cur.execute("SELECT user_id, is_admin FROM users WHERE user_id = %s", (user_id,))
        existing = cur.fetchone()
        
        if existing:
            # Actualizar usuario existente
            cur.execute("""
                UPDATE users 
                SET is_admin = TRUE, name = %s, email = %s, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s
            """, (name, email, user_id))
            print(f"✅ Usuario {user_id} actualizado como administrador")
        else:
            # Crear nuevo usuario administrador
            cur.execute("""
                INSERT INTO users (user_id, name, email, is_admin)
                VALUES (%s, %s, %s, TRUE)
            """, (user_id, name, email))
            
            # Crear wallet para el admin
            cur.execute("""
                INSERT INTO wallets (user_id, balance)
                VALUES (%s, 0.00)
            """, (user_id,))
            
            print(f"✅ Usuario administrador {user_id} creado exitosamente")
        
        conn.commit()
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python create_admin_user.py <user_id> [name] [email]")
        print("Ejemplo: python create_admin_user.py auth0|123456 'Admin User' admin@example.com")
        sys.exit(1)
    
    user_id = sys.argv[1]
    name = sys.argv[2] if len(sys.argv) > 2 else "Administrador"
    email = sys.argv[3] if len(sys.argv) > 3 else "admin@example.com"
    
    create_admin_user(user_id, name, email)

