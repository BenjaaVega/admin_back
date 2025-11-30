# Script PowerShell para iniciar los servicios necesarios para testear BONUS01

Write-Host "🚀 Iniciando servicios para BONUS01..." -ForegroundColor Cyan

# Verificar si Docker está corriendo
try {
    docker info | Out-Null
} catch {
    Write-Host "❌ Docker no está corriendo. Por favor inicia Docker Desktop." -ForegroundColor Red
    exit 1
}

# Cambiar al directorio del backend
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendPath = Join-Path $scriptPath ".."
Push-Location $backendPath

# Iniciar solo los servicios necesarios
Write-Host "📦 Iniciando auth_service y workers_service..." -ForegroundColor Yellow
docker-compose up -d auth_service workers_service

# Esperar a que los servicios estén listos
Write-Host "⏳ Esperando a que los servicios estén listos..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# Verificar que los servicios estén corriendo
$authRunning = docker ps --filter "name=auth_service" --format "{{.Names}}" | Select-String "auth_service"
$workersRunning = docker ps --filter "name=workers_service" --format "{{.Names}}" | Select-String "workers_service"

if ($authRunning -and $workersRunning) {
    Write-Host "✅ Servicios iniciados correctamente" -ForegroundColor Green
    Write-Host "   - auth_service: http://localhost:9000" -ForegroundColor White
    Write-Host "   - workers_service: http://localhost:9100" -ForegroundColor White
    Write-Host ""
    Write-Host "📋 Ejecuta el script de prueba:" -ForegroundColor Cyan
    Write-Host "   python scripts/test_bonus01.py" -ForegroundColor White
} else {
    Write-Host "❌ Error al iniciar los servicios" -ForegroundColor Red
    docker-compose logs auth_service workers_service
    exit 1
}

Pop-Location

