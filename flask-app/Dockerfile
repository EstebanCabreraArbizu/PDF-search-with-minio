# Usamos Python 3.11 como base (imagen oficial de Docker Hub)
FROM python:3.11-slim

# Instalar dependencias del sistema para PyMuPDF
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Establecer directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiar solo requirements.txt primero (para aprovechar cache de Docker)
COPY requirements.txt .

# Instalar dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Exponer el puerto 5000
EXPOSE 5000

# Comando para iniciar Flask
CMD ["python", "app.py"]