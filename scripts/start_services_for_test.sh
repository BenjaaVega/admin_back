#!/bin/bash
# Script para iniciar los servicios necesarios para testear BONUS01

echo "🚀 Iniciando servicios para BONUS01..."

# Verificar si Docker está corriendo
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker no está corriendo. Por favor inicia Docker Desktop."
    exit 1
fi

# Cambiar al directorio del backend
cd "$(dirname "$0")/.." || exit

# Iniciar solo los servicios necesarios
echo "📦 Iniciando auth_service y workers_service..."
docker-compose up -d auth_service workers_service

# Esperar a que los servicios estén listos
echo "⏳ Esperando a que los servicios estén listos..."
sleep 5

# Verificar que los servicios estén corriendo
if docker ps | grep -q "auth_service" && docker ps | grep -q "workers_service"; then
    echo "✅ Servicios iniciados correctamente"
    echo "   - auth_service: http://localhost:9000"
    echo "   - workers_service: http://localhost:9100"
    echo ""
    echo "📋 Ejecuta el script de prueba:"
    echo "   python scripts/test_bonus01.py"
else
    echo "❌ Error al iniciar los servicios"
    docker-compose logs auth_service workers_service
    exit 1
fi

