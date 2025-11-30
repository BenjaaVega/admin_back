#!/bin/bash
# Script de deployment optimizado para t3.micro (1GB RAM)
# Noviembre 2025

set -e

echo "🚀 Deployment de Workers Optimizado para t3.micro"
echo "=================================================="

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Verificar que estamos en el directorio correcto
if [ ! -f "docker-compose.workers.yml" ]; then
    echo -e "${RED}❌ Error: docker-compose.workers.yml no encontrado${NC}"
    echo "Asegúrate de estar en el directorio raíz del proyecto"
    exit 1
fi

echo -e "${YELLOW}📊 Estado actual del sistema:${NC}"
free -h
echo ""
df -h /
echo ""

echo -e "${YELLOW}🛑 Deteniendo contenedores existentes...${NC}"
docker-compose -f docker-compose.workers.yml down || true

echo -e "${YELLOW}🧹 Limpiando recursos no utilizados...${NC}"
# Limpiar imágenes y contenedores huérfanos para liberar espacio
docker system prune -f
docker image prune -a -f --filter "until=24h"

echo -e "${YELLOW}📥 Descargando imágenes actualizadas...${NC}"
docker-compose -f docker-compose.workers.yml pull

echo -e "${YELLOW}🏗️ Iniciando servicios optimizados...${NC}"
docker-compose -f docker-compose.workers.yml up -d

echo ""
echo -e "${YELLOW}⏳ Esperando que los servicios estén listos (30s)...${NC}"
sleep 30

echo ""
echo -e "${GREEN}✅ Servicios iniciados${NC}"
echo ""
docker-compose -f docker-compose.workers.yml ps

echo ""
echo -e "${YELLOW}📊 Uso de recursos:${NC}"
docker stats --no-stream

echo ""
echo -e "${GREEN}✅ Deployment completado!${NC}"
echo ""
echo "📌 URLs importantes:"
echo "   - JobMaster: http://localhost:8000"
echo "   - Flower Monitor: http://localhost:5555"
echo "   - Health Check: http://localhost:8000/heartbeat"
echo ""
echo "📝 Comandos útiles:"
echo "   - Ver logs: docker-compose -f docker-compose.workers.yml logs -f"
echo "   - Ver stats: docker stats"
echo "   - Reiniciar: docker-compose -f docker-compose.workers.yml restart"
echo ""
echo -e "${YELLOW}⚠️ Nota: Configurado para t3.micro con 1GB RAM${NC}"
echo "   - Solo 1 worker activo (worker2 deshabilitado)"
echo "   - Límites de memoria estrictos por contenedor"
echo "   - Pool mode: solo (sin multiprocessing)"
echo ""
