from flask import Flask, render_template, request, jsonify
from minio import Minio
from minio.error import S3Error
import fitz  # PyMuPDF
import os
import re
from datetime import timedelta
from urllib.parse import quote
app = Flask(__name__)

# ═══════════════════════════════════════════════════
# CONFIGURACIÓN MINIO (desde variables de entorno)
# ═══════════════════════════════════════════════════
MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'localhost:9000')
MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY', 'admin')
MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY', 'password123')
MINIO_PUBLIC_ENDPOINT = os.getenv("MINIO_PUBLIC_ENDPOINT", 'localhost:9000')

BUCKET_NAME = 'planillas-pdfs'
# Cliente MinIO
minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False  # True en producción con HTTPS
)

# minio_client_public = Minio(
# X -> llama a una ruta que no se encuentra minio -> localhost:9000
#     MINIO_PUBLIC_ENDPOINT,  # ← Usa el endpoint público directamente
#     access_key=MINIO_ACCESS_KEY,
#     secret_key=MINIO_SECRET_KEY,
#     secure=False
# )
# ════════════════════════════════════════════════
# INICIALIZACIÓN: Crear bucket si no existe
# ═══════════════════════════════════════════════════
def init_bucket():
    try:
        if not minio_client.bucket_exists(BUCKET_NAME):
            minio_client.make_bucket(BUCKET_NAME)
            print(f"✓ Bucket '{BUCKET_NAME}' creado")
        else:
            print(f"✓ Bucket '{BUCKET_NAME}' ya existe")
    except S3Error as e:
        print(f"✗ Error al crear bucket: {e}")

init_bucket()

# ═══════════════════════════════════════════════════
# FUNCIÓN: Extraer metadata de ruta de archivo
# ═══════════════════════════════════════════════════
def extract_metadata(file_path):
    """
    Extrae metadata de la ruta jerárquica:
    RESGUARDO/03.MARZO/BBVA/VACACIONES/planilla.pdf
    → {razon_social: 'RESGUARDO', mes: '03', banco: 'BBVA', ...}
    """
    parts = file_path.split('/')
    
    return {
        'razon_social': parts[0] if len(parts) > 0 else 'DESCONOCIDO',
        'mes': re.search(r'(\d{2})\.', parts[1]).group(1) if len(parts) > 1 and re.search(r'(\d{2})\.', parts[1]) else '00',
        'banco': parts[2] if len(parts) > 2 else 'GENERAL',
        'tipo_documento': parts[3] if len(parts) > 3 else 'GENERAL',
    }

# ═══════════════════════════════════════════════════
# FUNCIÓN: Buscar código de empleado en PDF
# ═══════════════════════════════════════════════════
def search_in_pdf(object_name, codigo_empleado):
    """Descarga y busca código en el PDF"""
    try:
        # Descargar PDF de MinIO
        response = minio_client.get_object(BUCKET_NAME, object_name)
        pdf_bytes = response.read()
        
        # Abrir PDF con PyMuPDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        # Buscar en cada página
        for page_num, page in enumerate(doc):
            text = page.get_text()
            # Patrón flexible para código de empleado
            pattern = rf'\b{re.escape(str(codigo_empleado))}\b'
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        return False
    except Exception as e:
        print(f"Error buscando en {object_name}: {e}")
        return False

# ═══════════════════════════════════════════════════
# RUTA: Página principal
# ═══════════════════════════════════════════════════
@app.route('/')
def index():
    return render_template('search.html')

# ═══════════════════════════════════════════════════
# RUTA: API de búsqueda
# ═══════════════════════════════════════════════════
@app.route('/api/search', methods=['POST'])
def search():
    """
    POST /api/search
    Body: {
        "codigo_empleado": "12345",
        "banco": "BBVA",
        "mes": "03",
        "razon_social": "RESGUARDO"
    }
    """
    filters = request.get_json()
    codigo_empleado = filters.get('codigo_empleado')
    
    results = []
    
    try:
        # Listar todos los objetos del bucket
        objects = minio_client.list_objects(BUCKET_NAME, recursive=True)
        
        for obj in objects:
            if not obj.object_name.endswith('.pdf'):
                continue
            
            # Extraer metadata de la ruta
            metadata = extract_metadata(obj.object_name)
            
            # Aplicar filtros de metadata
            if filters.get('banco') and metadata['banco'] != filters['banco']:
                continue
            if filters.get('mes') and metadata['mes'] != filters['mes']:
                continue
            if filters.get('razon_social') and metadata['razon_social'] != filters['razon_social']:
                continue
            
            # Si hay código de empleado, buscar dentro del PDF
            if codigo_empleado:
                if not search_in_pdf(obj.object_name, codigo_empleado):
                    continue
            
            
            internal_url = minio_client.presigned_get_object(
                BUCKET_NAME,
                obj.object_name,
                expires=timedelta(hours=1)
            )
            # Generar URL de descarga temporal
            download_url = internal_url.replace(
                f"http://{MINIO_ENDPOINT}",
                f"http://{MINIO_PUBLIC_ENDPOINT}"
            )

            
            results.append({
                'filename': obj.object_name,
                'metadata': metadata,
                'download_url': download_url,
                'size_kb': round(obj.size / 1024, 2)
            })
    
    except S3Error as e:
        return jsonify({'error': str(e)}), 500
    
    return jsonify({
        'total': len(results),
        'results': results
    })

# ═══════════════════════════════════════════════════
# RUTA: Subir PDFs de prueba (para desarrollo)
# ═══════════════════════════════════════════════════
@app.route('/api/upload', methods=['POST'])
def upload():
    """Endpoint para subir PDFs de prueba"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    file_path = request.form.get('path', file.filename)
    
    try:
        minio_client.put_object(
            BUCKET_NAME,
            file_path,
            file.stream,
            length=-1,
            part_size=10*1024*1024,
            content_type='application/pdf'
        )
        return jsonify({'message': f'Uploaded: {file_path}'}), 200
    except S3Error as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)