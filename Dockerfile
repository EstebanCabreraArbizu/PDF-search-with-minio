FROM python:3.11-slim

WORKDIR /app

# Dependencias del sistema para OCR
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-spa \
    poppler-utils \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Recolectar archivos estáticos
RUN python manage.py collectstatic --noinput

# Usar Gunicorn para producción
CMD ["gunicorn", "pdf_search_project.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]