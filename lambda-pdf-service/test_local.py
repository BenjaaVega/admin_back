#!/usr/bin/env python3
"""
Script de prueba local para verificar generación de PDFs
"""

import json
from handler import lambda_handler

# Evento de prueba
test_event = {
    "purchase_data": {
        "request_id": "test-local-12345",
        "amount": 150000,
        "status": "ACCEPTED",
        "created_at": "2024-11-03T10:30:00Z",
        "authorization_code": "ABC123XYZ"
    },
    "user_data": {
        "name": "Juan Pérez",
        "email": "juan.perez@example.com",
        "phone": "+56912345678"
    },
    "property_data": {
        "name": "Casa en Las Condes",
        "price": 1500000,
        "currency": "CLP",
        "url": "https://example.com/property/12345",
        "location": {
            "address": "Av. Apoquindo 1234, Las Condes"
        },
        "bedrooms": 3,
        "bathrooms": 2,
        "m2": 120
    },
    "group_id": "G6"
}

if __name__ == "__main__":
    print("🧪 Probando generación de PDF localmente...")
    print("=" * 60)
    
    # Simular contexto Lambda
    class Context:
        def __init__(self):
            self.function_name = "test-local"
            self.memory_limit_in_mb = 512
            self.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test"
            self.aws_request_id = "test-request-id"
    
    context = Context()
    
    try:
        # Llamar al handler
        response = lambda_handler(test_event, context)
        
        print("\n📊 Resultado:")
        print(json.dumps(response, indent=2))
        
        if response['statusCode'] == 200:
            body = json.loads(response['body'])
            print(f"\n✅ PDF generado exitosamente!")
            print(f"📄 URL: {body['pdf_url']}")
            print(f"🆔 Request ID: {body['request_id']}")
        else:
            body = json.loads(response['body'])
            print(f"\n❌ Error: {body.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"\n❌ Excepción: {str(e)}")
        import traceback
        traceback.print_exc()
