import json
import os
import boto3
import io
from datetime import datetime
from urllib.parse import quote
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER


def lambda_handler(event, context):
    """
    Función Lambda para generar boletas PDF y subirlas a S3
    """
    try:
        # Extraer datos del evento
        purchase_data = event.get('purchase_data', {})
        user_data = event.get('user_data', {})
        property_data = event.get('property_data', {})
        group_id = event.get('group_id', 'G6')

        # Validar datos requeridos
        if not purchase_data.get('request_id'):
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'request_id es requerido'})
            }

        # Generar PDF
        pdf_buffer = generate_pdf(purchase_data, user_data, property_data, group_id)

        # Verificar que el buffer tenga contenido
        pdf_buffer.seek(0)
        pdf_size = len(pdf_buffer.read())
        pdf_buffer.seek(0)
        print(f"PDF generado: {pdf_size} bytes")

        # Subir a S3
        s3_url = upload_to_s3(pdf_buffer, purchase_data['request_id'])
        print(f"PDF subido a S3: {s3_url}")

        return {
            'statusCode': 200,
            'body': json.dumps({
                'success': True,
                'pdf_url': s3_url,
                'request_id': purchase_data['request_id']
            })
        }

    except Exception as e:
        print(f"Error en lambda_handler: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def generate_pdf(purchase_data, user_data, property_data, group_id):
    """
    Genera el PDF de la boleta usando reportlab
    """
    buffer = io.BytesIO()

    # Crear documento PDF
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()

    # Estilos personalizados
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=30,
        alignment=TA_CENTER,
        textColor=colors.darkblue
    )

    header_style = ParagraphStyle(
        'CustomHeader',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=12,
        textColor=colors.darkgreen
    )

    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=6
    )

    # Contenido del PDF
    story = []

    # Título principal
    story.append(Paragraph(f"BOLETA DE COMPRA - GRUPO {group_id}", title_style))
    story.append(Spacer(1, 20))

    # Información de la compra
    story.append(Paragraph("INFORMACIÓN DE LA COMPRA", header_style))
    story.append(Paragraph(f"<b>ID de Solicitud:</b> {purchase_data.get('request_id', 'N/A')}", normal_style))
    story.append(Paragraph(f"<b>Fecha:</b> {purchase_data.get('created_at', datetime.now().isoformat())}", normal_style))
    # Formatear monto asegurándose de que sea un número
    amount = float(purchase_data.get('amount', 0))
    story.append(Paragraph(f"<b>Monto:</b> ${amount:,.2f} CLP", normal_style))
    story.append(Paragraph(f"<b>Estado:</b> {purchase_data.get('status', 'N/A')}", normal_style))
    if purchase_data.get('authorization_code'):
        story.append(Paragraph(f"<b>Código de Autorización:</b> {purchase_data['authorization_code']}", normal_style))
    story.append(Spacer(1, 20))

    # Información del usuario
    story.append(Paragraph("INFORMACIÓN DEL USUARIO", header_style))
    story.append(Paragraph(f"<b>Nombre:</b> {user_data.get('name', 'N/A')}", normal_style))
    story.append(Paragraph(f"<b>Email:</b> {user_data.get('email', 'N/A')}", normal_style))
    if user_data.get('phone'):
        story.append(Paragraph(f"<b>Teléfono:</b> {user_data['phone']}", normal_style))
    story.append(Spacer(1, 20))

    # Información de la propiedad
    if property_data:
        story.append(Paragraph("INFORMACIÓN DE LA PROPIEDAD", header_style))

        # Manejar el nombre con caracteres especiales
        prop_name = str(property_data.get('name', 'N/A')).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        story.append(Paragraph(f"<b>Nombre:</b> {prop_name}", normal_style))

        # Formatear precio asegurándose de que sea un número
        price = float(property_data.get('price', 0))
        currency = property_data.get('currency', 'CLP')
        story.append(Paragraph(f"<b>Precio:</b> ${price:,.2f} {currency}", normal_style))

        # Manejar URL con caracteres especiales
        prop_url = str(property_data.get('url', 'N/A')).replace('&', '&amp;')
        story.append(Paragraph(f"<b>URL:</b> {prop_url}", normal_style))

        if property_data.get('location'):
            location = property_data['location']
            if isinstance(location, dict):
                location_str = str(location.get('address', str(location))).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            else:
                location_str = str(location).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            story.append(Paragraph(f"<b>Ubicación:</b> {location_str}", normal_style))

        if property_data.get('bedrooms'):
            story.append(Paragraph(f"<b>Dormitorios:</b> {property_data['bedrooms']}", normal_style))
        if property_data.get('bathrooms'):
            story.append(Paragraph(f"<b>Baños:</b> {property_data['bathrooms']}", normal_style))
        if property_data.get('m2'):
            story.append(Paragraph(f"<b>Metros cuadrados:</b> {property_data['m2']}", normal_style))

    story.append(Spacer(1, 30))

    # Pie de página
    story.append(Paragraph(f"<i>Boleta generada automáticamente por el sistema del Grupo {group_id}</i>", normal_style))
    story.append(Paragraph(f"<i>Fecha de generación: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</i>", normal_style))

    # Construir PDF - ReportLab escribe directamente en el buffer
    doc.build(story)

    # Resetear posición del buffer al inicio para leer el contenido
    buffer.seek(0)

    # Verificar que el PDF sea válido
    pdf_data = buffer.getvalue()
    if len(pdf_data) == 0:
        raise ValueError("PDF generado está vacío")

    if not pdf_data.startswith(b'%PDF'):
        raise ValueError(f"PDF generado no es válido. Primeros bytes: {pdf_data[:20]}")

    print(f"✅ PDF generado exitosamente. Tamaño: {len(pdf_data)} bytes")

    return buffer


def upload_to_s3(pdf_buffer, request_id):
    """
    Sube el PDF a S3 y retorna la URL pública
    """
    s3_client = boto3.client('s3', region_name='us-east-1')
    bucket_name = os.getenv('S3_BUCKET', 'g6-arquisis-receipts-dev')

    # Nombre del archivo
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"receipts/boleta_{request_id}_{timestamp}.pdf"

    # Leer el contenido del buffer
    pdf_buffer.seek(0)
    pdf_data = pdf_buffer.read()

    # Validar que el PDF tenga contenido
    if len(pdf_data) == 0:
        raise ValueError("PDF buffer está vacío")

    # Verificar que sea un PDF válido (debe empezar con %PDF)
    if not pdf_data.startswith(b'%PDF'):
        raise ValueError(f"El buffer no contiene un PDF válido. Primeros bytes: {pdf_data[:10]}")

    print(f"📤 Subiendo PDF a S3: {filename} ({len(pdf_data)} bytes)")

    try:
        # Subir archivo a S3
        # Nota: No usamos ACL porque el bucket tiene ACLs deshabilitados
        # El acceso público se maneja mediante la política del bucket
        s3_client.put_object(
            Bucket=bucket_name,
            Key=filename,
            Body=pdf_data,
            ContentType='application/pdf',
            ContentDisposition='inline; filename="boleta.pdf"',
            CacheControl='public, max-age=31536000'
        )

        print(f"✅ PDF subido exitosamente a S3: s3://{bucket_name}/{filename}")

    except Exception as e:
        print(f"❌ Error subiendo PDF a S3: {str(e)}")
        raise

    # Generar URL pública
    encoded_key = quote(filename, safe='/')
    s3_url = f"https://{bucket_name}.s3.amazonaws.com/{encoded_key}"

    print(f"🔗 URL pública: {s3_url}")

    return s3_url
