from flask import Flask, render_template, request, jsonify, Response
from flask_jwt_extended import (
    JWTManager, create_access_token, 
    jwt_required, get_jwt_identity
)

from minio import Minio
from minio.error import S3Error
import fitz  # PyMuPDF
import os
import re
from datetime import timedelta
from models import db, User, DownloadLog

app = Flask(__name__)
# ═══════════════════════════════════════════════════
# CONFIGURACIÓN
# ═══════════════════════════════════════════════════
# Base de datos
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'DATABASE_URL', 
    'postgresql://admin:password123@localhost:5432/pdf_search'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# JWT
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'cambiar-en-produccion')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=8)

# MinIO
MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'minio:9000')
MINIO_PUBLIC_ENDPOINT = os.getenv('MINIO_PUBLIC_ENDPOINT', 'localhost:9000')
MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY', 'admin')
MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY', 'password123')
BUCKET_NAME = 'planillas-pdfs'

# Inicializar extensiones
db.init_app(app)
jwt = JWTManager(app)

# ═══════════════════════════════════════════════════
# MANEJADORES DE ERRORES JWT
# ═══════════════════════════════════════════════════
@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    """Cuando el token ha expirado"""
    app.logger.error(f"✗ ERROR JWT: Token expirado - Header: {jwt_header}")
    return jsonify({
        'error': 'Token expirado. Por favor inicia sesión nuevamente.',
        'total': 0,
        'results': []
    }), 401

@jwt.invalid_token_loader
def invalid_token_callback(error):
    """Cuando el token es inválido"""
    app.logger.error(f"✗ ERROR JWT: Token inválido - Error: {error}")
    return jsonify({
        'error': 'Token inválido. Por favor inicia sesión nuevamente.',
        'total': 0,
        'results': []
    }), 401

@jwt.unauthorized_loader
def missing_token_callback(error):
    """Cuando falta el token"""
    app.logger.error(f"✗ ERROR JWT: Token no proporcionado - Error: {error}")
    app.logger.error(f"Headers recibidos: {dict(request.headers)}")
    return jsonify({
        'error': 'Token no proporcionado. Por favor inicia sesión.',
        'total': 0,
        'results': []
    }), 401

# Cliente MinIO
minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False  # True en producción con HTTPS
)

# ════════════════════════════════════════════════
# INICIALIZACIÓN: Crear bucket si no existe
# ═══════════════════════════════════════════════════
def init_app():
    """Inicializa base de datos y MinIO"""
    with app.app_context():
        db.create_all()

        if not User.query.filter_by(username = "admin").first():
            admin = User(
                username = "admin",
                full_name = "Administrador",
                role = "admin"
            )
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
            app.logger.info("✓ Usuario admin creado (username: admin, password: admin123)")

    try:
        if not minio_client.bucket_exists(BUCKET_NAME):
            minio_client.make_bucket(BUCKET_NAME)
            app.logger.info(f"✓ Bucket '{BUCKET_NAME}' creado")
        else:
            app.logger.info(f"✓ Bucket '{BUCKET_NAME}' ya existe")
    except S3Error as e:
        app.logger.info(f"✗ Error al crear bucket: {e}")

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
        'razon_social': parts[0] if len(parts) > 0 else 'DESCONOCIDO', # posible uso de regex
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
        app.logger.info(f"Error buscando en {object_name}: {e}")
        return False

def log_download(user_id, filename, ip_address):
    """Registra descarga en auditoría"""
    log = DownloadLog(
        user_id=user_id,
        filename=filename,
        ip_address=ip_address
    )
    db.session.add(log)
    db.session.commit()

# ═══════════════════════════════════════════════════
# RUTAS DE AUTENTICACIÓN
# ═══════════════════════════════════════════════════
@app.route('/api/login', methods=['POST'])
def login():
    """
    Login de usuario
    Body: {"username": "admin", "password": "admin123"}
    """
    username = request.json.get('username')
    password = request.json.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Username y password requeridos'}), 400
    
    user = User.query.filter_by(username=username).first()
    
    if not user or not user.check_password(password):
        return jsonify({'error': 'Credenciales inválidas'}), 401
    
    if not user.is_active:
        return jsonify({'error': 'Usuario desactivado'}), 403
    
    # Crear JWT
    access_token = create_access_token(
        identity=str(user.id),  # ✅ Convertir a string
        additional_claims={
            'username': user.username,
            'role': user.role
        }
    )
    
    app.logger.info(f"✓ Login exitoso - Usuario: {user.username}, Token generado (primeros 20 chars): {access_token[:20]}...")
    
    return jsonify({
        'access_token': access_token,
        'user': user.to_dict()
    }), 200

@app.route('/api/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """Obtiene información del usuario actual"""
    user_id = int(get_jwt_identity())  # ← Convertir de string a int
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({'error': 'Usuario no encontrado'}), 404
    
    return jsonify(user.to_dict()), 200

# ═══════════════════════════════════════════════════
# RUTAS DE BÚSQUEDA Y DESCARGA (PROTEGIDAS)
# ═══════════════════════════════════════════════════
@app.route('/')
def index():
    return render_template('search.html')

@app.route('/api/search', methods=['POST'])
@jwt_required()  # ← Requiere autenticación
def search():
    """
    Búsqueda de PDFs (protegida)
    Body: {
        "codigo_empleado": "12345",
        "banco": "BBVA",
        "mes": "03",
        "razon_social": "RESGUARDO"
    }
    """
    # DEBUG: Ver qué usuario está haciendo la búsqueda
    user_id = int(get_jwt_identity())  # ← Convertir de string a int
    app.logger.info(f"✓ Búsqueda iniciada por user_id: {user_id}")
    
    filters = request.get_json() or {}
    codigo_empleado = filters.get('codigo_empleado')
    results = []
    
    try:
        objects = minio_client.list_objects(BUCKET_NAME, recursive=True)
        
        for obj in objects:
            if not obj.object_name.endswith('.pdf'):
                continue
            
            metadata = extract_metadata(obj.object_name)
            
            # Aplicar filtros
            if filters.get('banco') and metadata['banco'] != filters['banco']:
                continue
            if filters.get('mes') and metadata['mes'] != filters['mes']:
                continue
            if filters.get('razon_social') and metadata['razon_social'] != filters['razon_social']:
                continue
            
            if codigo_empleado:
                if not search_in_pdf(obj.object_name, codigo_empleado):
                    continue
            
            # ✅ URL de descarga apunta a endpoint protegido de Flask
            download_url = f"/api/download/{obj.object_name}"
            
            results.append({
                'filename': obj.object_name,
                'metadata': metadata,
                'download_url': download_url,
                'size_kb': round(obj.size / 1024, 2)
            })
    
    except S3Error as e:
        return jsonify({'error': str(e), 'total': 0, 'results': []}), 500
    except Exception as e:
        return jsonify({'error': f'Error inesperado: {str(e)}', 'total': 0, 'results': []}), 500
    
    return jsonify({'total': len(results), 'results': results})

@app.route('/api/download/<path:filename>', methods=['GET'])
@jwt_required()  # ← Requiere autenticación
def download_file(filename):
    """
    Descarga protegida: Flask actúa como proxy
    """
    user_id = int(get_jwt_identity())  # ← Convertir de string a int
    
    try:
        # Descargar de MinIO (conexión interna)
        response = minio_client.get_object(BUCKET_NAME, filename)
        
        # Registrar auditoría
        log_download(user_id, filename, request.remote_addr)
        
        # Enviar al usuario como stream
        return Response(
            response.stream(amt=8192),  # Chunks de 8KB
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="{filename.split("/")[-1]}"'
            }
        )
    except S3Error as e:
        return jsonify({'error': 'Archivo no encontrado'}), 404


# ═══════════════════════════════════════════════════
# RUTAS ADMIN (solo para rol 'admin')
# ═══════════════════════════════════════════════════
@app.route('/api/users', methods=['GET'])
@jwt_required()
def list_users():
    """Lista todos los usuarios (solo admin)"""
    # Obtener claims del JWT
    from flask_jwt_extended import get_jwt
    claims = get_jwt()
    
    if claims.get('role') != 'admin':
        return jsonify({'error': 'Permiso denegado'}), 403
    
    users = User.query.all()
    return jsonify([u.to_dict() for u in users]), 200

@app.route('/api/users', methods=['POST'])
@jwt_required()
def create_user():
    """Crea nuevo usuario (solo admin)"""
    from flask_jwt_extended import get_jwt
    claims = get_jwt()
    
    if claims.get('role') != 'admin':
        return jsonify({'error': 'Permiso denegado'}), 403
    
    data = request.get_json()
    
    # Validaciones
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'Usuario ya existe'}), 400
    
    user = User(
        username=data['username'],
        full_name=data.get('full_name'),
        role=data.get('role', 'user')
    )
    user.set_password(data['password'])
    
    db.session.add(user)
    db.session.commit()
    
    return jsonify(user.to_dict()), 201

@app.route('/api/logs', methods=['GET'])
@jwt_required()
def get_download_logs():
    """Obtiene logs de descargas (solo admin)"""
    from flask_jwt_extended import get_jwt
    claims = get_jwt()
    
    if claims.get('role') != 'admin':
        return jsonify({'error': 'Permiso denegado'}), 403
    
    logs = DownloadLog.query.order_by(DownloadLog.downloaded_at.desc()).limit(100).all()
    
    return jsonify([{
        'id': log.id,
        'username': log.user.username,
        'filename': log.filename,
        'downloaded_at': log.downloaded_at.isoformat(),
        'ip_address': log.ip_address
    } for log in logs]), 200

if __name__ == '__main__':
    init_app()
    # Con JWT_SECRET_KEY fijo en docker-compose, ya no hay problema con hot-reload
    app.run(host='0.0.0.0', port=5000, debug=True)