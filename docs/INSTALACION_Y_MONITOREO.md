# Documentación de Instalación y Monitoreo - G6 Arquisis Backend

## Tabla de Contenidos
1. [Descripción General](#descripción-general)
2. [Arquitectura del Sistema](#arquitectura-del-sistema)
3. [Prerrequisitos](#prerrequisitos)
4. [Instalación Local](#instalación-local)
5. [Instalación en AWS EC2](#instalación-en-aws-ec2)
6. [Configuración de Variables de Entorno](#configuración-de-variables-de-entorno)
7. [Despliegue con Docker](#despliegue-con-docker)
8. [Configuración de API Gateway](#configuración-de-api-gateway)
9. [Configuración de Nginx](#configuración-de-nginx)
10. [Flujo de Monitoreo](#flujo-de-monitoreo)
11. [Troubleshooting](#troubleshooting)
12. [Comandos Útiles](#comandos-útiles)

## Descripción General

Esta aplicación es un backend desarrollado en FastAPI que maneja propiedades inmobiliarias, usuarios, wallets y un sistema de solicitudes de visitas. Utiliza PostgreSQL como base de datos y MQTT para comunicación asíncrona.

**URL de la Aplicación Web:** https://www.iic2173-e0-repablo6.me/

**URL de la API:** https://api.api-g6.tech

### Componentes Principales:
- **API FastAPI**: Endpoints REST para gestión de propiedades, usuarios y wallets
- **MQTT Listener**: Procesa mensajes asíncronos de propiedades y solicitudes
- **Base de Datos PostgreSQL**: Almacena datos de propiedades, usuarios, transacciones y solicitudes
- **Docker**: Contenedor de la aplicación
- **AWS EC2**: Servidor de producción
- **API Gateway**: Proxy para el frontend

## Arquitectura del Sistema

```
Frontend (CloudFront) → API Gateway → Nginx → FastAPI (Docker)
                                    ↓
                               PostgreSQL (Docker)
                                    ↓
                               MQTT Listener (Docker)
                                    ↓
                               MQTT Broker (Externo)
```

## Prerrequisitos

### Local
- Docker y Docker Compose
- Git
- Python 3.12+ (para desarrollo)

### AWS EC2
- Instancia EC2 con Ubuntu
- Docker y Docker Compose instalados
- Claves SSH configuradas
- API Gateway configurado

## Instalación Local

### 1. Clonar el Repositorio
```bash
git clone https://github.com/giacop002/g6_arquisis_back.git
cd g6_arquisis_back
```

### 2. Configurar Variables de Entorno
Configurar archivo `.env` 
```

### 3. Ejecutar con Docker
```bash
docker-compose up --build -d
```

### 4. Verificar Instalación
```bash
# Verificar contenedores
docker-compose ps

# Verificar logs
docker-compose logs api_1
docker-compose logs mqtt_listener

# Probar endpoints
curl http://localhost:8001/health
curl http://localhost:8001/properties
```

## Instalación en AWS EC2

### 1. Conectar a la Instancia
```bash
ssh -i "clave.pem" ubuntu@ec2-instance.amazonaws.com
```

### 2. Instalar Dependencias
```bash
# Actualizar sistema
sudo apt update && sudo apt upgrade -y

# Instalar Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ubuntu

# Instalar Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Instalar Nginx
sudo apt install nginx -y
```

### 3. Clonar y Configurar Aplicación
```bash
cd ~
git clone https://github.com/giacop002/g6_arquisis_back.git
cd g6_arquisis_back

# Configurar .env con credenciales de producción
nano .env
```

### 4. Configurar Nginx
```bash
# Crear configuración de Nginx
sudo nano /etc/nginx/sites-available/fastapi_app

# Contenido del archivo de configuración:
```

```nginx
upstream fastapi_backends {
    server 127.0.0.1:8001;
    server 127.0.0.1:8002;
}

server {
    listen 80;
    server_name tu-dominio.com www.tu-dominio.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name tu-dominio.com www.tu-dominio.com;
    
    ssl_certificate /etc/letsencrypt/live/tu-dominio.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/tu-dominio.com/privkey.pem;
    
    location / {
        proxy_pass http://fastapi_backends;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Configuración para API Gateway
server {
    listen 80 default_server;
    server_name ec2-instance.amazonaws.com IP_ADDRESS _;
    
    location / {
        proxy_pass http://127.0.0.1:8001/;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
    }
}
```

```bash
# Habilitar configuración
sudo ln -s /etc/nginx/sites-available/fastapi_app /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default

# Reiniciar Nginx
sudo systemctl restart nginx
sudo systemctl enable nginx
```

## Configuración de Variables de Entorno

### Variables Requeridas
```bash
# MQTT Configuration
BROKER=
MQTT_PORT=
MQTT_USERNAME=
MQTT_PASSWORD=
REQUESTS_TOPIC=
VALIDATION_TOPIC=
INFO_TOPIC=
GROUP_ID=

# Database Configuration
DB_NAME=
DB_USER=
DB_PASSWORD=
DB_HOST=
DB_PORT=

# FastAPI Configuration
FASTAPI_HOST=
FASTAPI_PORT=

# Frontend Configuration
FRONTEND_ORIGIN=
# Auth0 Configuration
AUTH0_DOMAIN=
AUTH0_AUDIENCE=

# Allowed Origins
ALLOWED_ORIGINS=
```

## Despliegue con Docker

### 1. Construir y Ejecutar Contenedores
```bash
# Construir imágenes
docker-compose build

# Ejecutar en background
docker-compose up -d

# Verificar estado
docker-compose ps
```

### 2. Inicializar Base de Datos
```bash
# Ejecutar script de inicialización
docker exec -it postgres_db psql -U legit_user -d legitbusiness -f /docker-entrypoint-initdb.d/init.sql
```

### 3. Verificar Servicios
```bash
# Ver logs de todos los servicios
docker-compose logs

# Ver logs específicos
docker-compose logs api_1
docker-compose logs mqtt_listener
docker-compose logs postgres_db
```

## Configuración de API Gateway

### 1. Crear API Gateway
- Crear nueva API REST en AWS API Gateway
- Configurar recursos y métodos (GET, POST, PUT, DELETE)
- Configurar integración HTTP Proxy

### 2. Configurar Métodos
Para cada endpoint:
- **Integration Type**: HTTP Proxy
- **Endpoint URL**: `http://ec2-instance-ip/endpoint`
- **HTTP Method**: ANY (para proxy)
- **Enable HTTP Proxy Integration**: Sí

### 3. Desplegar API
- Crear stage "produccion"
- Obtener URL de invocación
- Configurar CORS en el backend

## Configuración de Nginx

### 1. Configuración para API Gateway
```nginx
server {
    listen 80 default_server;
    server_name ec2-instance.amazonaws.com IP_ADDRESS _;
    
    access_log /var/log/nginx/apigw_access.log;
    error_log /var/log/nginx/apigw_error.log;
    
    location / {
        proxy_pass http://127.0.0.1:8001/;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
    }
}
```

### 2. Verificar Configuración
```bash
# Probar configuración
sudo nginx -t

# Reiniciar Nginx
sudo systemctl restart nginx

# Ver logs
sudo tail -f /var/log/nginx/apigw_access.log
sudo tail -f /var/log/nginx/apigw_error.log
```

## Flujo de Monitoreo

### 1. Monitoreo de Estado de Servicios

#### Verificar Contenedores
```bash
# Estado de contenedores
docker-compose ps

# Logs en tiempo real
docker-compose logs -f

# Logs específicos
docker-compose logs api_1 | tail -50
docker-compose logs mqtt_listener | tail -50
```

#### Verificar Salud de la API
```bash
# Endpoint de salud
curl https://api.api-g6.tech/health

# Endpoint de base de datos
curl https://api.api-g6.tech/health/db

# Endpoint de autenticación
curl -H "Authorization: Bearer token" https://api.api-g6.tech/auth/test
```

### 2. Monitoreo de Base de Datos

#### Verificar Conexión
```bash
# Conectar a PostgreSQL
docker exec -it postgres_db psql -U legit_user -d legitbusiness

# Verificar tablas
\dt

# Ver conteo de registros
SELECT 'properties' as tabla, COUNT(*) as registros FROM properties
UNION ALL
SELECT 'users', COUNT(*) FROM users
UNION ALL
SELECT 'wallets', COUNT(*) FROM wallets
UNION ALL
SELECT 'transactions', COUNT(*) FROM transactions
UNION ALL
SELECT 'purchase_requests', COUNT(*) FROM purchase_requests;
```

#### Monitoreo de Solicitudes
```bash
# Ver solicitudes recientes
SELECT 
    request_id, 
    user_id, 
    group_id, 
    url, 
    status, 
    created_at 
FROM purchase_requests 
ORDER BY created_at DESC 
LIMIT 10;

# Ver conteo por estado
SELECT 
    status, 
    COUNT(*) as cantidad 
FROM purchase_requests 
GROUP BY status;
```

### 3. Monitoreo de MQTT

#### Verificar Conexión MQTT
```bash
# Logs del MQTT listener
docker-compose logs mqtt_listener | grep -i "conectado\|broker"

# Ver mensajes procesados
docker-compose logs mqtt_listener | grep -E "(UPDATE|INSERT) properties"

# Ver errores MQTT
docker-compose logs mqtt_listener | grep -i "error\|exception"
```

#### Monitoreo de Propiedades
```bash
# Ver propiedades con visit_slots
SELECT 
    url, 
    name, 
    visit_slots, 
    timestamp 
FROM properties 
ORDER BY timestamp DESC 
LIMIT 10;

# Total de slots disponibles
SELECT SUM(visit_slots) as total_slots_disponibles FROM properties;
```

### 4. Scripts de Monitoreo Automatizado

#### Script de Monitoreo General
```bash
#!/bin/bash
echo "=== MONITOREO GENERAL DEL SISTEMA ==="
echo "Timestamp: $(date)"
echo ""

echo "1. ESTADO DE CONTENEDORES:"
docker-compose ps

echo ""
echo "2. SALUD DE LA API:"
curl -s https://api.api-g6.tech/health | jq .

echo ""
echo "3. CONEXIÓN A BASE DE DATOS:"
curl -s https://api.api-g6.tech/health/db | jq .

echo ""
echo "4. ESTADÍSTICAS DE BASE DE DATOS:"
docker exec postgres_db psql -U legit_user -d legitbusiness -c "
SELECT 'properties' as tabla, COUNT(*) as registros FROM properties
UNION ALL
SELECT 'users', COUNT(*) FROM users
UNION ALL
SELECT 'purchase_requests', COUNT(*) FROM purchase_requests;
"

echo ""
echo "5. ÚLTIMOS LOGS MQTT:"
docker-compose logs mqtt_listener | grep -E "(UPDATE|INSERT) properties" | tail -3

echo ""
echo "=== FIN DEL MONITOREO ==="
```

#### Script de Monitoreo de Solicitudes
```bash
#!/bin/bash
echo "=== MONITOREO DE SOLICITUDES ==="
echo "Timestamp: $(date)"
echo ""

echo "1. SOLICITUDES RECIENTES:"
docker exec postgres_db psql -U legit_user -d legitbusiness -c "
SELECT 
    request_id, 
    user_id, 
    group_id, 
    url, 
    status, 
    created_at 
FROM purchase_requests 
ORDER BY created_at DESC 
LIMIT 5;
"

echo ""
echo "2. CONTEO POR ESTADO:"
docker exec postgres_db psql -U legit_user -d legitbusiness -c "
SELECT 
    status, 
    COUNT(*) as cantidad 
FROM purchase_requests 
GROUP BY status;
"

echo ""
echo "3. ÚLTIMOS LOGS API (solicitudes):"
docker-compose logs api_1 | grep -i "request\|visits" | tail -3

echo ""
echo "=== FIN DEL MONITOREO ==="
```

## Troubleshooting

### Problemas Comunes

#### 1. Error de Conexión a Base de Datos
```bash
# Verificar que PostgreSQL esté ejecutándose
docker-compose ps postgres_db

# Ver logs de PostgreSQL
docker-compose logs postgres_db

# Verificar variables de entorno
docker exec api_1 env | grep DB_
```

#### 2. Error de Conexión MQTT
```bash
# Verificar configuración MQTT
docker-compose logs mqtt_listener | grep -i "conectado\|error"

# Verificar variables de entorno
docker exec mqtt_listener env | grep MQTT_
```

#### 3. Error de CORS
```bash
# Verificar configuración CORS en el código
grep -r "CORS\|origins" api/main.py

# Verificar headers en las respuestas
curl -I https://api.api-g6.tech/health
```

#### 4. Error de Autenticación Auth0
```bash
# Verificar configuración Auth0
docker exec api_1 env | grep AUTH0_

# Probar endpoint de autenticación
curl -H "Authorization: Bearer token" https://api.api-g6.tech/auth/test
```

### Comandos de Diagnóstico

#### Verificar Estado General
```bash
# Estado de contenedores
docker-compose ps

# Uso de recursos
docker stats

# Logs de errores
docker-compose logs | grep -i error
```

#### Verificar Red
```bash
# Conectividad a base de datos
docker exec api_1 ping db

# Conectividad a MQTT
docker exec mqtt_listener ping broker.iic2173.org

# Conectividad externa
curl -I https://api.api-g6.tech/health
```

## Comandos Útiles

### Gestión de Contenedores
```bash
# Ver estado
docker-compose ps

# Reiniciar servicios
docker-compose restart api_1 api_2 mqtt_listener

# Ver logs
docker-compose logs -f api_1
docker-compose logs -f mqtt_listener

# Ejecutar comandos en contenedores
docker exec -it postgres_db psql -U legit_user -d legitbusiness
docker exec -it api_1 bash
```

### Gestión de Base de Datos
```bash
# Conectar a PostgreSQL
docker exec -it postgres_db psql -U legit_user -d legitbusiness

# Ver estructura de tablas
\dt
\d properties
\d users
\d purchase_requests

# Ver conteos
SELECT COUNT(*) FROM properties;
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM purchase_requests;

# Limpiar datos (¡CUIDADO!)
DELETE FROM purchase_requests WHERE status = 'ERROR';
```

### Gestión de Logs
```bash
# Ver logs en tiempo real
docker-compose logs -f

# Ver logs específicos
docker-compose logs api_1 | grep -i error
docker-compose logs mqtt_listener | grep -i "properties"

# Limpiar logs
docker-compose logs --tail=0 -f
```

### Actualización del Sistema
```bash
# Hacer pull de cambios
git pull origin main

# Reconstruir contenedores
docker-compose up --build -d

# Verificar cambios
docker-compose ps
docker-compose logs api_1 | tail -20
```

---

## Notas Importantes

1. **Seguridad**: Nunca incluir credenciales en la documentación
2. **Backups**: Realizar backups regulares de la base de datos
3. **Monitoreo**: Ejecutar scripts de monitoreo regularmente
4. **Logs**: Revisar logs periódicamente para detectar problemas
5. **Actualizaciones**: Mantener el sistema actualizado con las últimas versiones

## Limitaciones Conocidas

### Monitoreo con New Relic (No Implementado)

**Requerimiento:** Implementar monitoreo utilizando un proveedor de monitoreo SaaS (New Relic recomendado) con:
- Monitoreo de infraestructura
- Monitoreo de aplicación
- Dashboard principal de New Relic

**Estado:** No implementado completamente

**Razón:** Durante el desarrollo del proyecto, se intentó configurar New Relic APM para el monitoreo de la aplicación FastAPI, pero no se logró completar la integración debido a:

1. **Complejidad de configuración**: La integración de New Relic APM con FastAPI en contenedores Docker requirió modificaciones en la arquitectura del proyecto.

2. **Limitaciones de tiempo**: El tiempo disponible para el desarrollo no permitió resolver completamente los problemas de configuración.

3. **Configuración parcial lograda**: Se logró instalar y configurar el New Relic Infrastructure Agent, que monitorea la infraestructura del servidor (CPU, memoria, disco, red), pero no se completó la configuración del APM para la aplicación.


**Alternativas:**
- Monitoreo manual mediante scripts de bash
- Logs estructurados con Docker Compose
- Endpoints de salud (`/health`, `/health/db`)
- Monitoreo de base de datos mediante consultas SQL directas

