# 📦 Guía de Despliegue Lambda con Serverless Framework

## 🎯 Descripción del Servicio

Este documento describe paso a paso cómo desplegar el **Servicio de Generación de Boletas PDF** en AWS Lambda utilizando Serverless Framework.

### **¿Qué hace el servicio?**
- ✅ Genera boletas PDF profesionales con ReportLab
- ✅ Sube PDFs a bucket S3 público
- ✅ Retorna URL pública del PDF generado
- ✅ Expone endpoint HTTP vía API Gateway

### **Arquitectura:**
```
FastAPI Backend → Invoca Lambda → Genera PDF → Sube a S3 → Retorna URL pública
```

---

## 📋 Requisitos Previos

### 1. **Software Necesario**

| Herramienta | Versión Requerida | Comando de Verificación |
|-------------|-------------------|-------------------------|
| Node.js | ≥ 18.x | `node --version` |
| npm | ≥ 9.x | `npm --version` |
| Python | 3.11 | `python --version` |
| AWS CLI | ≥ 2.x | `aws --version` |

### 2. **Credenciales AWS**

Debes tener configuradas credenciales AWS con permisos para:
- ✅ Lambda (crear/actualizar funciones)
- ✅ S3 (crear buckets, subir objetos)
- ✅ API Gateway (crear/actualizar APIs)
- ✅ CloudFormation (crear stacks)
- ✅ IAM (crear roles para Lambda)

---

## 🚀 Instalación Inicial (Primera Vez)

### **Paso 1: Instalar Serverless Framework Globalmente**

```bash
npm install -g serverless
```

**Verificar instalación:**
```bash
serverless --version
```

**Salida esperada:**
```
Framework Core: 3.38.0
Plugin: 6.2.3
SDK: 4.3.2
```

---

### **Paso 2: Navegar al Directorio del Servicio**

```bash
cd lambda-pdf-service
```

**Estructura esperada:**
```
lambda-pdf-service/
├── handler.py              # Función Lambda principal
├── requirements.txt        # Dependencias Python
├── serverless.yml          # Configuración Serverless
├── package.json           # Dependencias Node
└── package-lock.json
```

---

### **Paso 3: Instalar Dependencias Node.js**

```bash
npm install
```

Esto instalará:
- `serverless` (framework)
- `serverless-python-requirements` (plugin para empaquetar Python)

**Verificar package.json:**
```json
{
  "devDependencies": {
    "serverless": "^3.38.0",
    "serverless-python-requirements": "^6.0.0"
  }
}
```

---

### **Paso 4: Configurar Credenciales AWS**

#### **Opción A: Usando AWS CLI (Recomendado)**

```bash
aws configure
```

Te pedirá:
```
AWS Access Key ID [None]: AKIAIOSFODNN7EXAMPLE
AWS Secret Access Key [None]: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
Default region name [None]: us-east-1
Default output format [None]: json
```

#### **Opción B: Variables de Entorno**

```bash
# Windows PowerShell
$env:AWS_ACCESS_KEY_ID="AKIAIOSFODNN7EXAMPLE"
$env:AWS_SECRET_ACCESS_KEY="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
$env:AWS_DEFAULT_REGION="us-east-1"

# Linux/Mac
export AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
export AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
export AWS_DEFAULT_REGION=us-east-1
```

**Verificar credenciales:**
```bash
aws sts get-caller-identity
```

**Salida esperada:**
```json
{
    "UserId": "AIDAI...",
    "Account": "123456789012",
    "Arn": "arn:aws:iam::123456789012:user/tu-usuario"
}
```

---

## 🔧 Configuración del Servicio

### **Paso 5: Revisar serverless.yml**

El archivo `serverless.yml` define toda la infraestructura:

```yaml
service: g6-arquisis-pdf-service

provider:
  name: aws
  runtime: python3.11
  region: us-east-1
  stage: ${opt:stage, 'dev'}  # dev por defecto
  timeout: 30                  # Timeout de 30 segundos
  memorySize: 512             # 512 MB de RAM

functions:
  generateReceipt:
    handler: handler.lambda_handler
    events:
      - http:
          path: /generate-receipt
          method: post
          cors: true

resources:
  Resources:
    ReceiptsBucket:
      Type: AWS::S3::Bucket
      Properties:
        BucketName: g6-arquisis-receipts-${self:provider.stage}
```

**Componentes clave:**
- 📦 **Función Lambda**: `generateReceipt`
- 🌐 **API Gateway**: Endpoint HTTP POST
- 🪣 **S3 Bucket**: `g6-arquisis-receipts-dev` (o `-prod`)
- 🔐 **Políticas IAM**: Permisos para S3

---

### **Paso 6: Validar Configuración**

```bash
serverless print
```

Este comando:
- ✅ Valida sintaxis de `serverless.yml`
- ✅ Muestra la configuración compilada
- ✅ Detecta errores antes del deploy

**Si hay errores:**
```
Error: Missing required property 'handler'
```
Revisa el archivo `serverless.yml` y corrige.

---

## 🚀 Despliegue a AWS

### **Paso 7: Deploy a Desarrollo (Dev)**

```bash
serverless deploy --stage dev --verbose
```

**¿Qué hace este comando?**
1. **Empaqueta código Python**:
   - Instala dependencias de `requirements.txt`
   - Crea un archivo .zip con el código

2. **Sube a S3**:
   - Sube el .zip a bucket temporal de Serverless

3. **Crea/actualiza CloudFormation Stack**:
   - Crea función Lambda
   - Crea API Gateway
   - Crea bucket S3 para PDFs
   - Configura permisos IAM

4. **Despliega recursos**:
   - Lambda Function: `g6-arquisis-pdf-service-dev-generateReceipt`
   - S3 Bucket: `g6-arquisis-receipts-dev`
   - API Gateway: Endpoint HTTP público

**Salida esperada:**
```
✔ Service deployed to stack g6-arquisis-pdf-service-dev (112s)

endpoints:
  POST - https://abc123def456.execute-api.us-east-1.amazonaws.com/dev/generate-receipt

functions:
  generateReceipt: g6-arquisis-pdf-service-dev-generateReceipt (5.2 MB)
```

**⚠️ Guardar el endpoint URL** - Lo necesitarás para configurar el backend.

---

### **Paso 8: Deploy a Producción (Prod)**

```bash
serverless deploy --stage prod --verbose
```

**Diferencias con Dev:**
- Bucket S3: `g6-arquisis-receipts-prod`
- Función Lambda: `g6-arquisis-pdf-service-prod-generateReceipt`
- Endpoint separado: `https://xyz789.execute-api.us-east-1.amazonaws.com/prod/generate-receipt`

**Salida esperada:**
```
✔ Service deployed to stack g6-arquisis-pdf-service-prod (118s)

endpoints:
  POST - https://xyz789abc123.execute-api.us-east-1.amazonaws.com/prod/generate-receipt

functions:
  generateReceipt: g6-arquisis-pdf-service-prod-generateReceipt (5.2 MB)
```

---

## 🧪 Pruebas del Servicio

### **Paso 9: Probar Localmente (Opcional)**

```bash
serverless invoke local -f generateReceipt -d '{
  "purchase_data": {
    "request_id": "test-123",
    "amount": 100000,
    "status": "ACCEPTED",
    "created_at": "2024-01-01T00:00:00Z"
  },
  "user_data": {
    "name": "Usuario Test",
    "email": "test@example.com"
  },
  "property_data": {
    "name": "Casa Test",
    "price": 1000000,
    "url": "https://example.com/property"
  },
  "group_id": "G6"
}'
```

**Salida esperada:**
```json
{
    "statusCode": 200,
    "body": "{\"success\": true, \"pdf_url\": \"...\", \"request_id\": \"test-123\"}"
}
```

---

### **Paso 10: Probar en AWS (Remoto)**

#### **Opción A: Usando Serverless Invoke**

```bash
serverless invoke -f generateReceipt --stage dev -d '{
  "purchase_data": {
    "request_id": "test-aws-456",
    "amount": 150000,
    "status": "ACCEPTED",
    "created_at": "2024-01-01T00:00:00Z"
  },
  "user_data": {
    "name": "Usuario AWS Test",
    "email": "test-aws@example.com"
  },
  "property_data": {
    "name": "Departamento Test",
    "price": 1500000,
    "url": "https://example.com/property"
  },
  "group_id": "G6"
}'
```

#### **Opción B: Usando cURL (HTTP Endpoint)**

```bash
curl -X POST https://abc123def456.execute-api.us-east-1.amazonaws.com/dev/generate-receipt \
  -H "Content-Type: application/json" \
  -d '{
    "purchase_data": {
      "request_id": "test-http-789",
      "amount": 200000,
      "status": "ACCEPTED",
      "created_at": "2024-01-01T00:00:00Z",
      "authorization_code": "ABC123"
    },
    "user_data": {
      "name": "Usuario HTTP Test",
      "email": "test-http@example.com"
    },
    "property_data": {
      "name": "Casa HTTP Test",
      "price": 2000000,
      "url": "https://example.com/property",
      "location": {"address": "Calle Falsa 123"},
      "bedrooms": 3,
      "bathrooms": 2,
      "m2": 120
    },
    "group_id": "G6"
  }'
```

**Respuesta esperada:**
```json
{
  "success": true,
  "pdf_url": "https://g6-arquisis-receipts-dev.s3.amazonaws.com/receipts/boleta_test-http-789_20250103_143022.pdf",
  "request_id": "test-http-789"
}
```

#### **Opción C: Verificar PDF Generado**

Abre el `pdf_url` en tu navegador:
```
https://g6-arquisis-receipts-dev.s3.amazonaws.com/receipts/boleta_test-http-789_20250103_143022.pdf
```

Deberías ver un PDF con:
- ✅ Título "BOLETA DE COMPRA - GRUPO G6"
- ✅ Información de la compra (request_id, fecha, monto, estado)
- ✅ Información del usuario (nombre, email)
- ✅ Información de la propiedad (nombre, precio, ubicación, etc.)

---

## 📊 Monitoreo y Logs

### **Ver Logs de Lambda**

```bash
# Logs en tiempo real
serverless logs -f generateReceipt --stage dev --tail

# Últimas 100 líneas
serverless logs -f generateReceipt --stage dev --startTime 1h
```

**Salida:**
```
2024-01-03 14:30:22.123  START RequestId: abc-123-def-456
2024-01-03 14:30:22.456  [INFO] Generando PDF para request_id: test-123
2024-01-03 14:30:23.789  [INFO] PDF subido a S3: receipts/boleta_test-123_...
2024-01-03 14:30:23.890  END RequestId: abc-123-def-456
2024-01-03 14:30:23.891  REPORT Duration: 1768.23 ms  Billed Duration: 1769 ms  Memory Size: 512 MB  Max Memory Used: 187 MB
```

---

### **Ver Métricas en AWS Console**

1. Ir a **AWS Console → Lambda**
2. Seleccionar función: `g6-arquisis-pdf-service-dev-generateReceipt`
3. Pestaña **Monitor**
4. Ver métricas:
   - Invocaciones
   - Duración promedio
   - Errores
   - Throttles

---

### **Ver Objetos en S3**

```bash
# Listar PDFs generados
aws s3 ls s3://g6-arquisis-receipts-dev/receipts/

# Descargar PDF específico
aws s3 cp s3://g6-arquisis-receipts-dev/receipts/boleta_test-123_20250103_143022.pdf ./boleta_test.pdf
```

---

## 🔄 Actualización del Servicio

### **Modificar Código y Re-desplegar**

1. **Editar `handler.py`** con tus cambios

2. **Validar sintaxis Python:**
   ```bash
   python -m py_compile handler.py
   ```

3. **Re-desplegar:**
   ```bash
   serverless deploy --stage dev --verbose
   ```

**⚡ Deploy incremental:** Solo sube cambios, no recrea toda la infraestructura (~30-60 segundos).

---

### **Actualizar Solo la Función (Más Rápido)**

```bash
serverless deploy function -f generateReceipt --stage dev
```

**Ventaja:** Solo actualiza el código de la función (~10-15 segundos).

**⚠️ Limitación:** No actualiza configuración de API Gateway, buckets, etc.

---

## 🗑️ Eliminar el Servicio

### **Eliminar Stack Completo**

```bash
# Desarrollo
serverless remove --stage dev

# Producción
serverless remove --stage prod
```

**¿Qué elimina?**
- ✅ Función Lambda
- ✅ API Gateway
- ✅ Roles IAM
- ✅ CloudFormation Stack
- ⚠️ **S3 Bucket** (solo si está vacío)

**Si el bucket tiene PDFs:**
```bash
# Vaciar bucket antes de eliminar
aws s3 rm s3://g6-arquisis-receipts-dev/receipts/ --recursive

# Ahora eliminar el servicio
serverless remove --stage dev
```

---

## 🔗 Integración con Backend FastAPI

### **Paso 11: Configurar Variable de Entorno**

En tu archivo `.env` del backend API:

```bash
# Para desarrollo
LAMBDA_PDF_ENDPOINT=https://abc123def456.execute-api.us-east-1.amazonaws.com/dev/generate-receipt

# Para producción
LAMBDA_PDF_ENDPOINT=https://xyz789abc123.execute-api.us-east-1.amazonaws.com/prod/generate-receipt
```

---

### **Paso 12: Invocar Lambda desde FastAPI**

En `api/main.py`, el código actual invoca Lambda:

```python
import requests

LAMBDA_PDF_ENDPOINT = os.getenv('LAMBDA_PDF_ENDPOINT', '')

def generate_pdf_receipt(purchase_data, user_data, property_data):
    """Invoca Lambda para generar PDF de boleta"""
    if not LAMBDA_PDF_ENDPOINT:
        print("⚠️ LAMBDA_PDF_ENDPOINT no configurado")
        return None
    
    payload = {
        "purchase_data": purchase_data,
        "user_data": user_data,
        "property_data": property_data,
        "group_id": "G6"
    }
    
    try:
        response = requests.post(LAMBDA_PDF_ENDPOINT, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"❌ Error invocando Lambda: {e}")
        return None
```

**Uso en endpoint de confirmación de compra:**
```python
@app.post("/purchases/validate")
def validate_purchase(request: PurchaseValidationRequest):
    # ... lógica de validación ...
    
    # Generar PDF
    pdf_result = generate_pdf_receipt(
        purchase_data={
            "request_id": str(request_id),
            "amount": amount,
            "status": "ACCEPTED",
            "created_at": datetime.now().isoformat()
        },
        user_data={"name": user_name, "email": user_email},
        property_data=property_info
    )
    
    if pdf_result and pdf_result.get('success'):
        pdf_url = pdf_result['pdf_url']
        print(f"✅ PDF generado: {pdf_url}")
    
    # ... continuar con lógica ...
```

---

## 🛠️ Troubleshooting

### **Error: "Unable to import module 'handler'"**

**Causa:** Dependencias no empaquetadas correctamente.

**Solución:**
```bash
# Limpiar cache
rm -rf .serverless node_modules package-lock.json

# Reinstalar
npm install

# Re-desplegar
serverless deploy --stage dev
```

---

### **Error: "Bucket already exists"**

**Causa:** El bucket S3 ya existe (de un deploy anterior).

**Solución:**
```bash
# Opción 1: Usar otro stage
serverless deploy --stage dev2

# Opción 2: Eliminar bucket manualmente
aws s3 rb s3://g6-arquisis-receipts-dev --force
```

---

### **Error: "Access Denied" al subir a S3**

**Causa:** Permisos IAM insuficientes.

**Solución:** Verificar que el rol de Lambda tenga:
```yaml
iam:
  role:
    statements:
      - Effect: Allow
        Action:
          - s3:PutObject
          - s3:PutObjectAcl
        Resource: "arn:aws:s3:::g6-arquisis-receipts-${self:provider.stage}/*"
```

Re-desplegar:
```bash
serverless deploy --stage dev --force
```

---

### **Error: "Timeout after 30 seconds"**

**Causa:** Lambda tarda más de 30 segundos.

**Solución:** Aumentar timeout en `serverless.yml`:
```yaml
provider:
  timeout: 60  # 60 segundos
  memorySize: 1024  # Más RAM = más rápido
```

---

### **PDFs no son públicos**

**Causa:** Política del bucket no configurada correctamente.

**Solución:** Verificar en `serverless.yml`:
```yaml
resources:
  Resources:
    ReceiptsBucketPolicy:
      Type: AWS::S3::BucketPolicy
      Properties:
        Bucket: !Ref ReceiptsBucket
        PolicyDocument:
          Statement:
            - Effect: Allow
              Principal: "*"
              Action: s3:GetObject
              Resource: !Join ["", ["arn:aws:s3:::", !Ref ReceiptsBucket, "/*"]]
```

---

## 📦 Comandos de Referencia Rápida

```bash
# Instalar Serverless globalmente
npm install -g serverless

# Instalar dependencias del proyecto
cd lambda-pdf-service && npm install

# Validar configuración
serverless print

# Deploy a desarrollo
serverless deploy --stage dev --verbose

# Deploy a producción
serverless deploy --stage prod --verbose

# Ver logs en tiempo real
serverless logs -f generateReceipt --stage dev --tail

# Invocar función remotamente
serverless invoke -f generateReceipt --stage dev -d '{"purchase_data": {...}}'

# Actualizar solo función (rápido)
serverless deploy function -f generateReceipt --stage dev

# Eliminar stack completo
serverless remove --stage dev

# Ver información del stack
serverless info --stage dev

# Ver métricas
serverless metrics --stage dev
```

---

## 📚 Recursos Adicionales

### **Documentación Oficial**
- [Serverless Framework Docs](https://www.serverless.com/framework/docs)
- [AWS Lambda Developer Guide](https://docs.aws.amazon.com/lambda/latest/dg/welcome.html)
- [ReportLab Documentation](https://www.reportlab.com/docs/reportlab-userguide.pdf)

### **Plugins Útiles**
- `serverless-offline`: Simular Lambda localmente
- `serverless-python-requirements`: Empaquetar dependencias Python
- `serverless-plugin-tracing`: Habilitar AWS X-Ray

### **Best Practices**
- ✅ Usar variables de entorno para configuración
- ✅ Implementar logging estructurado
- ✅ Configurar alarmas CloudWatch
- ✅ Usar layers para dependencias grandes
- ✅ Implementar retry logic para S3 uploads

---

## 🎓 Glosario

| Término | Definición |
|---------|------------|
| **Lambda** | Servicio serverless de AWS para ejecutar código sin gestionar servidores |
| **Serverless Framework** | Herramienta para desplegar aplicaciones serverless |
| **API Gateway** | Servicio para crear y gestionar APIs HTTP |
| **CloudFormation** | Infraestructura como código de AWS |
| **Stack** | Conjunto de recursos AWS desplegados juntos |
| **Stage** | Ambiente de despliegue (dev, prod, test) |
| **Handler** | Función principal que Lambda ejecuta |
| **Layer** | Paquete de dependencias compartido entre funciones |

---

**Última actualización:** Noviembre 2025  
**Versión:** 1.0  
**Equipo:** Grupo 6 - Arquitecturas de Software Intensivas
