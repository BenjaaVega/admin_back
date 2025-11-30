# mqtt_listener/Dockerfile
FROM python:3.12-slim

# Instalar dependencias del sistema necesarias para psycopg2
RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# Definir directorio de trabajo
WORKDIR /app

# Copiar requirements y luego instalar
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Comando por defecto para ejecutar el listener
CMD ["python", "mqtt_listener.py"]