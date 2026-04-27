#!/bin/bash
# Script para rebuildar Docker tras cambios en estáticos o dependencias

set -e  # Salir en caso de error

echo "═══════════════════════════════════════════════════════════"
echo "REBUILD DOCKER - Estáticos y Dependencias"
echo "═══════════════════════════════════════════════════════════"

# Detener contenedores
echo "🛑 Deteniendo contenedores..."
docker-compose down

# Rebuild Node.js service (frontend build)
echo "🏗️  Rebuildando servicio Node.js..."
docker-compose build --no-cache node

# Rebuild Django service
echo "🏗️  Rebuildando servicio Django..."
docker-compose build --no-cache django

# Iniciar servicios
echo "🚀 Iniciando servicios..."
docker-compose up -d

# Esperar a que Django esté listo
echo "⏳ Esperando a que Django inicie..."
sleep 5

# Recolectar estáticos si es necesario
echo "📦 Recolectando estáticos..."
docker-compose exec -T django python manage.py collectstatic --noinput

echo "✅ Rebuild completado!"
echo "═══════════════════════════════════════════════════════════"
