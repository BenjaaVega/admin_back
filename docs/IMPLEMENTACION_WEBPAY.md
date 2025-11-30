# Implementación de WebPay

## Pasos seguidos para la implementación

### 1. Instalación de dependencias

Se agregó el SDK de Transbank al archivo `requirements.txt`:
```
transbank-sdk>=3.0.0
```

### 2. Creación del servicio WebPay

Se creó el archivo `api/webpay_service.py` con la clase `WebPayService` que incluye:

- Configuración para ambiente de integración (TEST)
- Credenciales por defecto para testing:
  - Commerce Code: `597055555532`
  - API Key: `579B532A7440BB0C9079DED94D31EA1615BACEB56610332264630D42D0A36B1C`
- Tres métodos principales:
  - `create_transaction()`: Crea una nueva transacción
  - `commit_transaction()`: Confirma una transacción
  - `get_transaction_status()`: Obtiene el estado de una transacción

### 3. Integración en la API principal

En `api/main.py` se agregaron:

- Importación del servicio WebPay
- Instanciación global del servicio
- Modelos Pydantic para las requests y responses:
  - `WebPayCreateRequest`
  - `WebPayCreateResponse`
  - `WebPayCommitRequest`
  - `WebPayCommitResponse`

### 4. Endpoints implementados

Se crearon tres endpoints principales:

#### POST `/webpay/create`
- Valida el monto (debe ser 10% del precio de la propiedad)
- Verifica disponibilidad de cupos
- Genera IDs únicos para la transacción
- Crea la transacción en WebPay
- Retorna token y URL de pago

#### POST `/webpay/commit`
- Confirma la transacción con el token recibido
- Si es exitosa (response_code = 0):
  - Crea purchase_request en estado PENDING
  - Reduce visit_slots de la propiedad
  - Registra transacción en BD
  - Publica mensaje MQTT
  - Registra evento en event_log

#### GET `/webpay/status/{token}`
- Consulta el estado de una transacción específica

#### GET `/webpay/return`
- Maneja el retorno desde WebPay
- Verifica el estado de la transacción

### 5. Configuración de variables de entorno

Se configuraron variables opcionales:
- `WEBPAY_COMMERCE_CODE`: Código de comercio
- `WEBPAY_API_KEY`: Clave API
- `FRONTEND_ORIGIN`: URL base del frontend para URLs de retorno

### 6. Flujo de integración

1. Usuario solicita crear transacción WebPay con monto y URL de propiedad
2. Sistema valida monto (10% del precio) y disponibilidad
3. Se crea transacción en WebPay y se retorna token/URL
4. Usuario completa pago en WebPay
5. WebPay redirige a `/webpay/return` con token
6. Frontend llama a `/webpay/commit` con token y URL de propiedad
7. Sistema confirma transacción y procesa reserva si es exitosa

### 7. Manejo de errores

- Validación de montos y disponibilidad
- Rollback de cambios si falla publicación MQTT
- Manejo de transacciones rechazadas
- Logging de eventos en event_log
