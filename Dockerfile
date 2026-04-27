FROM python:3.11-slim

WORKDIR /app

# Dependencias del sistema para OCR y Node.js
RUN apt-get update && apt-get install -y \
    curl \
    tesseract-ocr \
    tesseract-ocr-spa \
    poppler-utils \
    libpq-dev \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Variables para NPM y ejecución del build frontend
ARG NPM_GITHUB_TOKEN
ENV NPM_GITHUB_TOKEN=${NPM_GITHUB_TOKEN}
RUN npm install && npm run build

# Recolectar archivos estáticos
RUN python manage.py collectstatic --noinput

# Usar Gunicorn para producción
CMD ["gunicorn", "pdf_search_project.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "300"]