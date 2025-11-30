FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app/workers_service

CMD ["uvicorn", "workers_service.main:app", "--host", "0.0.0.0", "--port", "9100"]


