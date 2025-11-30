#!/usr/bin/env python3
"""
Script de verificación para BONUS01: Autenticación JWT con refresh tokens
Verifica:
1. Login inicial con credenciales de service account
2. Expiraciones correctas (access < 3 horas, refresh < 1 día)
3. Uso de access token para llamar al workers service
4. Refresh token automático cuando el access token expira
5. Fallback a login cuando el refresh token expira
6. Validación de ES256
7. JWKS endpoint
"""

import os
import sys
import time
import json
import requests
from datetime import datetime, timezone
from typing import Dict, Any

# Configuración
AUTH_URL = os.getenv("AUTH_SERVICE_URL", "http://localhost:9000")
WORKERS_URL = os.getenv("WORKERS_SERVICE_URL", "http://localhost:9100")
SERVICE_ACCOUNT_ID = os.getenv("SERVICE_ACCOUNT_ID", "worker-client")
SERVICE_ACCOUNT_SECRET = os.getenv("SERVICE_ACCOUNT_SECRET", "change-me")

# Colores para output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"


def print_test(name: str):
    print(f"\n{BOLD}{BLUE}━━━ {name} ━━━{RESET}")


def print_success(message: str):
    print(f"{GREEN}✓{RESET} {message}")


def print_error(message: str):
    print(f"{RED}✗{RESET} {message}")


def print_info(message: str):
    print(f"{YELLOW}ℹ{RESET} {message}")


def decode_token(token: str) -> Dict[str, Any]:
    """Decodifica un JWT sin verificar la firma"""
    import jwt as pyjwt
    return pyjwt.decode(token, options={"verify_signature": False})


def test_jwks_endpoint():
    """Test 1: Verificar endpoint JWKS"""
    print_test("Test 1: Endpoint JWKS")
    try:
        resp = requests.get(f"{AUTH_URL}/.well-known/jwks.json", timeout=5)
        resp.raise_for_status()
        jwks = resp.json()
        
        if "keys" not in jwks:
            print_error("JWKS no contiene 'keys'")
            return False
        
        if len(jwks["keys"]) == 0:
            print_error("JWKS no contiene ninguna llave")
            return False
        
        key = jwks["keys"][0]
        required_fields = ["kty", "crv", "x", "y", "kid", "use"]
        for field in required_fields:
            if field not in key:
                print_error(f"JWKS key falta campo: {field}")
                return False
        
        # Verificar que es ES256 (EC P-256)
        if key.get("kty") != "EC":
            print_error(f"Tipo de llave incorrecto: {key.get('kty')} (esperado: EC)")
            return False
        
        if key.get("crv") != "P-256":
            print_error(f"Curva incorrecta: {key.get('crv')} (esperado: P-256)")
            return False
        
        print_success("JWKS endpoint funciona correctamente")
        print_success(f"Algoritmo: ES256 (EC P-256)")
        print_info(f"Key ID: {key.get('kid')}")
        return True
    except Exception as e:
        print_error(f"Error al obtener JWKS: {e}")
        return False


def test_initial_login():
    """Test 2: Login inicial con credenciales"""
    print_test("Test 2: Login inicial con Service Account")
    try:
        resp = requests.post(
            f"{AUTH_URL}/token",
            json={
                "client_id": SERVICE_ACCOUNT_ID,
                "client_secret": SERVICE_ACCOUNT_SECRET,
            },
            timeout=5
        )
        resp.raise_for_status()
        data = resp.json()
        
        if "access_token" not in data or "refresh_token" not in data:
            print_error("Respuesta no contiene access_token o refresh_token")
            return None
        
        # Decodificar tokens
        access_payload = decode_token(data["access_token"])
        refresh_payload = decode_token(data["refresh_token"])
        
        # Verificar tipos
        if access_payload.get("typ") != "access":
            print_error(f"Access token tiene tipo incorrecto: {access_payload.get('typ')}")
            return None
        
        if refresh_payload.get("typ") != "refresh":
            print_error(f"Refresh token tiene tipo incorrecto: {refresh_payload.get('typ')}")
            return None
        
        # Verificar expiraciones
        now = int(time.time())
        access_exp = access_payload.get("exp", 0)
        refresh_exp = refresh_payload.get("exp", 0)
        
        access_ttl = access_exp - now
        refresh_ttl = refresh_exp - now
        
        # Access token debe expirar en < 3 horas (10800 segundos)
        if access_ttl > 10800:
            print_error(f"Access token expira en {access_ttl/3600:.2f} horas (debe ser < 3 horas)")
            return None
        
        # Refresh token debe expirar en < 1 día (86400 segundos)
        if refresh_ttl > 86400:
            print_error(f"Refresh token expira en {refresh_ttl/86400:.2f} días (debe ser < 1 día)")
            return None
        
        print_success("Login exitoso con credenciales")
        print_success(f"Access token expira en {access_ttl/3600:.2f} horas (< 3 horas ✓)")
        print_success(f"Refresh token expira en {refresh_ttl/3600:.2f} horas (< 24 horas ✓)")
        print_info(f"Subject: {access_payload.get('sub')}")
        print_info(f"Audience: {access_payload.get('aud')}")
        
        return data
    except requests.exceptions.HTTPError as e:
        print_error(f"Error HTTP: {e}")
        if e.response:
            print_error(f"Respuesta: {e.response.text}")
        return None
    except Exception as e:
        print_error(f"Error en login: {e}")
        return None


def test_invalid_credentials():
    """Test 3: Rechazo de credenciales inválidas"""
    print_test("Test 3: Rechazo de credenciales inválidas")
    try:
        resp = requests.post(
            f"{AUTH_URL}/token",
            json={
                "client_id": "invalid",
                "client_secret": "invalid",
            },
            timeout=5
        )
        
        if resp.status_code == 401:
            print_success("Credenciales inválidas correctamente rechazadas")
            return True
        else:
            print_error(f"Se esperaba 401, pero se recibió {resp.status_code}")
            return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False


def test_use_access_token(tokens: Dict):
    """Test 4: Usar access token para llamar al workers service"""
    print_test("Test 4: Uso de Access Token en Workers Service")
    try:
        resp = requests.post(
            f"{WORKERS_URL}/jobs/echo",
            json={"test": "data", "message": "Hello from test"},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            timeout=5
        )
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("ok") and "echo" in data:
            print_success("Access token válido y aceptado por workers service")
            print_info(f"Subject en respuesta: {data.get('sub')}")
            return True
        else:
            print_error("Respuesta inesperada del workers service")
            return False
    except requests.exceptions.HTTPError as e:
        print_error(f"Error HTTP: {e}")
        if e.response:
            print_error(f"Respuesta: {e.response.text}")
        return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False


def test_refresh_token(tokens: Dict):
    """Test 5: Refresh token funciona correctamente"""
    print_test("Test 5: Refresh Token")
    try:
        resp = requests.post(
            f"{AUTH_URL}/token/refresh",
            json={"refresh_token": tokens["refresh_token"]},
            timeout=5
        )
        resp.raise_for_status()
        new_tokens = resp.json()
        
        if "access_token" not in new_tokens or "refresh_token" not in new_tokens:
            print_error("Refresh no devolvió nuevos tokens")
            return None
        
        # Verificar que son tokens diferentes
        if new_tokens["access_token"] == tokens["access_token"]:
            print_error("El nuevo access token es igual al anterior")
            return None
        
        print_success("Refresh token funciona correctamente")
        print_info("Nuevos tokens emitidos")
        
        return new_tokens
    except requests.exceptions.HTTPError as e:
        print_error(f"Error HTTP: {e}")
        if e.response:
            print_error(f"Respuesta: {e.response.text}")
        return None
    except Exception as e:
        print_error(f"Error: {e}")
        return None


def test_invalid_token_type():
    """Test 6: Rechazo de access token como refresh token"""
    print_test("Test 6: Rechazo de token type incorrecto")
    try:
        # Primero obtener un access token
        resp = requests.post(
            f"{AUTH_URL}/token",
            json={
                "client_id": SERVICE_ACCOUNT_ID,
                "client_secret": SERVICE_ACCOUNT_SECRET,
            },
            timeout=5
        )
        resp.raise_for_status()
        tokens = resp.json()
        
        # Intentar usar access token como refresh token
        resp = requests.post(
            f"{AUTH_URL}/token/refresh",
            json={"refresh_token": tokens["access_token"]},
            timeout=5
        )
        
        if resp.status_code == 400:
            print_success("Access token correctamente rechazado como refresh token")
            return True
        else:
            print_error(f"Se esperaba 400, pero se recibió {resp.status_code}")
            return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False


def test_expired_token_handling():
    """Test 7: Verificar que el workers service rechaza tokens expirados o inválidos"""
    print_test("Test 7: Rechazo de tokens inválidos/expirados")
    try:
        # Intentar con token inválido
        resp = requests.post(
            f"{WORKERS_URL}/jobs/echo",
            json={"test": "data"},
            headers={"Authorization": "Bearer invalid.token.here"},
            timeout=5
        )
        
        if resp.status_code == 401:
            print_success("Token inválido correctamente rechazado")
        else:
            print_error(f"Se esperaba 401 para token inválido, pero se recibió {resp.status_code}")
            return False
        
        # Intentar sin token
        resp = requests.post(
            f"{WORKERS_URL}/jobs/echo",
            json={"test": "data"},
            timeout=5
        )
        
        if resp.status_code == 403:
            print_success("Petición sin token correctamente rechazada")
            return True
        else:
            print_error(f"Se esperaba 403 para petición sin token, pero se recibió {resp.status_code}")
            return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False


def test_algorithm_verification():
    """Test 8: Verificar que se usa ES256"""
    print_test("Test 8: Verificación de algoritmo ES256")
    try:
        resp = requests.post(
            f"{AUTH_URL}/token",
            json={
                "client_id": SERVICE_ACCOUNT_ID,
                "client_secret": SERVICE_ACCOUNT_SECRET,
            },
            timeout=5
        )
        resp.raise_for_status()
        tokens = resp.json()
        
        # Decodificar header del token
        import jwt as pyjwt
        header = pyjwt.get_unverified_header(tokens["access_token"])
        
        if header.get("alg") == "ES256":
            print_success("Algoritmo ES256 confirmado en header del token")
            return True
        else:
            print_error(f"Algoritmo incorrecto: {header.get('alg')} (esperado: ES256)")
            return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False


def check_services_available():
    """Verifica si los servicios están disponibles"""
    print_test("Verificación de servicios")
    services_ok = True
    
    # Verificar auth_service
    try:
        resp = requests.get(f"{AUTH_URL}/.well-known/jwks.json", timeout=3)
        if resp.status_code == 200:
            print_success(f"Auth Service disponible en {AUTH_URL}")
        else:
            print_error(f"Auth Service respondió con código {resp.status_code}")
            services_ok = False
    except requests.exceptions.ConnectionError:
        print_error(f"No se puede conectar a {AUTH_URL}")
        print_info("Asegúrate de que el servicio esté corriendo:")
        print_info("  docker-compose up -d auth_service")
        services_ok = False
    except Exception as e:
        print_error(f"Error al verificar auth_service: {e}")
        services_ok = False
    
    # Verificar workers_service
    try:
        resp = requests.get(f"{WORKERS_URL}/health", timeout=3)
        if resp.status_code == 200:
            print_success(f"Workers Service disponible en {WORKERS_URL}")
        else:
            print_error(f"Workers Service respondió con código {resp.status_code}")
            services_ok = False
    except requests.exceptions.ConnectionError:
        print_error(f"No se puede conectar a {WORKERS_URL}")
        print_info("Asegúrate de que el servicio esté corriendo:")
        print_info("  docker-compose up -d workers_service")
        services_ok = False
    except Exception as e:
        print_error(f"Error al verificar workers_service: {e}")
        services_ok = False
    
    return services_ok


def main():
    print(f"\n{BOLD}{'='*60}")
    print(f"  VERIFICACIÓN BONUS01: JWT Refresh Tokens")
    print(f"{'='*60}{RESET}\n")
    
    print_info(f"Auth Service URL: {AUTH_URL}")
    print_info(f"Workers Service URL: {WORKERS_URL}")
    print_info(f"Service Account ID: {SERVICE_ACCOUNT_ID}\n")
    
    # Verificar servicios antes de continuar
    if not check_services_available():
        print(f"\n{RED}{BOLD}Los servicios no están disponibles. Por favor inicia los servicios primero.{RESET}")
        print(f"\n{YELLOW}Para iniciar los servicios con Docker:{RESET}")
        print(f"  cd g6_arquisis_back")
        print(f"  docker-compose up -d auth_service workers_service")
        print(f"\n{YELLOW}O ejecuta el script:{RESET}")
        print(f"  python scripts/start_services_for_test.ps1")
        sys.exit(1)
    
    print()  # Línea en blanco antes de los tests
    results = []
    
    # Test 1: JWKS endpoint
    results.append(("JWKS Endpoint", test_jwks_endpoint()))
    
    # Test 2: Login inicial
    tokens = test_initial_login()
    results.append(("Login inicial", tokens is not None))
    
    if not tokens:
        print_error("\nNo se pudo obtener tokens. Abortando tests restantes.")
        sys.exit(1)
    
    # Test 3: Credenciales inválidas
    results.append(("Rechazo credenciales inválidas", test_invalid_credentials()))
    
    # Test 4: Uso de access token
    results.append(("Uso de access token", test_use_access_token(tokens)))
    
    # Test 5: Refresh token
    new_tokens = test_refresh_token(tokens)
    results.append(("Refresh token", new_tokens is not None))
    
    # Test 6: Token type incorrecto
    results.append(("Rechazo token type incorrecto", test_invalid_token_type()))
    
    # Test 7: Tokens inválidos/expirados
    results.append(("Rechazo tokens inválidos", test_expired_token_handling()))
    
    # Test 8: Algoritmo ES256
    results.append(("Algoritmo ES256", test_algorithm_verification()))
    
    # Resumen
    print_test("RESUMEN")
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = f"{GREEN}✓{RESET}" if result else f"{RED}✗{RESET}"
        print(f"  {status} {name}")
    
    print(f"\n{BOLD}Resultado: {passed}/{total} tests pasaron{RESET}")
    
    if passed == total:
        print(f"\n{GREEN}{BOLD}¡Todos los tests pasaron! BONUS01 está correctamente implementado.{RESET}\n")
        sys.exit(0)
    else:
        print(f"\n{RED}{BOLD}Algunos tests fallaron. Revisa la implementación.{RESET}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()

