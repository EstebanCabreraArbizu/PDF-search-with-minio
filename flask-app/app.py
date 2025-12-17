from flask import Flask, render_template, request, jsonify, Response
from flask_jwt_extended import (
    JWTManager, create_access_token, 
    jwt_required, get_jwt_identity
)
from datetime import datetime, timedelta
from minio import Minio
from minio.error import S3Error
import fitz  # PyMuPDF
import os
import re
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
# CONSTANTES: Mapeo de razones sociales para estandarización
# ═══════════════════════════════════════════════════
# Mapeo de variaciones a nombre estandarizado (normalizado a MAYÚSCULAS)
RAZONES_SOCIALES_MAP = {
    # Variaciones con numeración → Nombre estandarizado
    'J & V RESGUARDO': 'RESGUARDO',
    'J&V RESGUARDO': 'RESGUARDO',
    'RESGUARDO': 'RESGUARDO',
    'ALARMAS': 'ALARMAS',
    'AZZARO': 'AZZARO',
    'FACILITIES': 'FACILITIES',
    'LIDERMAN SERVICIOS': 'LIDERMAN SERVICIOS',
    'LIDERMAN': 'LIDERMAN SERVICIOS',
    'SELVA': 'SELVA',
}

# Lista de razones sociales válidas para el frontend
RAZONES_SOCIALES_VALIDAS = sorted(set(RAZONES_SOCIALES_MAP.values()))

# Bancos válidos
BANCOS_VALIDOS = ['BBVA', 'BCP', 'INTERBANK', 'SCOTIABANK']

# ═══════════════════════════════════════════════════
# FUNCIÓN: Normalizar razón social
# ═══════════════════════════════════════════════════
def normalize_razon_social(raw_name):
    """
    Estandariza nombres de razones sociales que pueden tener:
    - Numeración: "1. J & V Resguardo" → "RESGUARDO"
    - Variaciones de escritura: "J&V RESGUARDO" → "RESGUARDO"
    - Mayúsculas/minúsculas inconsistentes
    
    Ejemplos:
        "1. J & V Resguardo"  → "RESGUARDO"
        "02.ALARMAS"          → "ALARMAS"
        "Liderman Servicios"  → "LIDERMAN SERVICIOS"
        "RESGUARDO"           → "RESGUARDO"
    """
    if not raw_name:
        return 'DESCONOCIDO'
    
    # 1. Remover numeración inicial: "1. ", "02.", "10. ", etc.
    cleaned = re.sub(r'^\d+[\.\s\-]+', '', raw_name.strip())
    
    # 2. Convertir a mayúsculas para comparación
    cleaned_upper = cleaned.upper().strip()
    
    # 3. Buscar en el mapeo (intenta coincidencia exacta primero)
    if cleaned_upper in RAZONES_SOCIALES_MAP:
        return RAZONES_SOCIALES_MAP[cleaned_upper]
    
    # 4. Buscar coincidencia parcial (si contiene alguna clave del mapeo)
    for key, standard_name in RAZONES_SOCIALES_MAP.items():
        if key in cleaned_upper or cleaned_upper in key:
            return standard_name
    
    # 5. Si no hay match, retornar el nombre limpio en mayúsculas
    app.logger.warning(f"⚠️ Razón social no reconocida: '{raw_name}' → usando '{cleaned_upper}'")
    return cleaned_upper

# ═══════════════════════════════════════════════════
# FUNCIÓN: Extraer año de carpeta madre
# ═══════════════════════════════════════════════════
def extract_year_from_path(path_part):
    """
    Extrae el año de carpetas como:
    - "Planillas 2019-2025" → "2024" (año actual o más reciente válido)
    - "Planillas 2023"      → "2023"
    - "2024"                → "2024"
    
    Para rangos como "2019-2025", retorna el año más reciente del rango
    que no exceda el año actual.
    """
    if not path_part:
        return None
    
    # Buscar rango de años: "2019-2025"
    range_match = re.search(r'(\d{4})\s*[-–]\s*(\d{4})', path_part)
    if range_match:
        start_year = int(range_match.group(1))
        end_year = int(range_match.group(2))
        current_year = datetime.now().year
        # Retornar el año más reciente que no exceda el actual
        return str(min(end_year, current_year))
    
    # Buscar año simple: "2023", "Planillas 2023", etc.
    year_match = re.search(r'(20\d{2})', path_part)
    if year_match:
        return year_match.group(1)
    
    return None

# ═══════════════════════════════════════════════════
# FUNCIÓN: Extraer metadata de ruta de archivo (MEJORADA)
# ═══════════════════════════════════════════════════
def extract_metadata(file_path):
    """
    Extrae metadata de la ruta jerárquica con soporte para:
    
    ESTRUCTURA NUEVA (con carpeta de año):
    Planillas 2019-2025/1. J & V Resguardo/03.MARZO/BBVA/VACACIONES/planilla.pdf
    → {año: '2025', razon_social: 'RESGUARDO', mes: '03', banco: 'BBVA', tipo_documento: 'VACACIONES'}
    
    ESTRUCTURA ACTUAL (sin carpeta de año):
    RESGUARDO/03.MARZO/BBVA/VACACIONES/planilla.pdf
    → {año: '2025' (actual), razon_social: 'RESGUARDO', mes: '03', banco: 'BBVA', tipo_documento: 'VACACIONES'}
    """
    parts = file_path.split('/')
    
    # Detectar si la primera carpeta contiene un año
    año = None
    offset = 0  # Desplazamiento de índices si hay carpeta de año
    
    if len(parts) > 0:
        potential_year = extract_year_from_path(parts[0])
        if potential_year:
            año = potential_year
            offset = 1  # La estructura empieza en parts[1]
    
    # Si no hay año en la carpeta, usar el año actual
    if not año:
        año = str(datetime.now().year)
    
    # Extraer razón social (con normalización)
    razon_social_raw = parts[offset] if len(parts) > offset else 'DESCONOCIDO'
    razon_social = normalize_razon_social(razon_social_raw)
    
    # Extraer mes del patrón "03.MARZO", "01.ENERO", etc.
    mes_raw = parts[offset + 1] if len(parts) > offset + 1 else ''
    mes_match = re.search(r'(\d{2})\.', mes_raw)
    mes = mes_match.group(1) if mes_match else '00'
    
    # Extraer banco (normalizado a mayúsculas)
    banco_raw = parts[offset + 2] if len(parts) > offset + 2 else 'GENERAL'
    # Limpiar subcarpetas dentro del banco: "BBVA/FM2/QNA" → "BBVA"
    banco = banco_raw.split('/')[0].upper().strip()
    # Validar que sea un banco conocido
    if banco not in BANCOS_VALIDOS:
        # Intentar encontrar banco válido en el path
        for parte in parts:
            parte_upper = parte.upper()
            for banco_valido in BANCOS_VALIDOS:
                if banco_valido in parte_upper:
                    banco = banco_valido
                    break
    
    # Extraer tipo de documento
    tipo_documento_raw = parts[offset + 3] if len(parts) > offset + 3 else 'GENERAL'
    tipo_documento = tipo_documento_raw.upper().strip()
    
    return {
        'año': año,
        'razon_social': razon_social,
        'mes': mes,
        'banco': banco,
        'tipo_documento': tipo_documento,
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
# HEALTH CHECK (para monitoreo de IT/Nginx)
# ═══════════════════════════════════════════════════
@app.route('/health')
def health_check():
    """Endpoint para verificar que la aplicación está funcionando"""
    try:
        # Verificar conexión a PostgreSQL
        db.session.execute(db.text('SELECT 1'))
        db_status = 'ok'
    except Exception as e:
        db_status = f'error: {str(e)}'
    
    try:
        # Verificar conexión a MinIO
        minio_client.bucket_exists(BUCKET_NAME)
        minio_status = 'ok'
    except Exception as e:
        minio_status = f'error: {str(e)}'
    
    status = 'ok' if db_status == 'ok' and minio_status == 'ok' else 'degraded'
    
    return jsonify({
        'status': status,
        'timestamp': datetime.utcnow().isoformat(),
        'services': {
            'database': db_status,
            'storage': minio_status
        }
    }), 200 if status == 'ok' else 503

# ═══════════════════════════════════════════════════
# RUTAS DE BÚSQUEDA Y DESCARGA (PROTEGIDAS)
# ═══════════════════════════════════════════════════
@app.route('/')
def index():
    return render_template('search.html')

@app.route('/api/filter-options', methods=['GET'])
@jwt_required()
def get_filter_options():
    """
    Retorna las opciones disponibles para los filtros de búsqueda.
    Útil para poblar los selectores del frontend dinámicamente.
    
    Response: {
        "años": ["2024", "2023", "2022", ...],
        "razones_sociales": ["ALARMAS", "FACILITIES", ...],
        "bancos": ["BBVA", "BCP", ...],
        "meses": [{"value": "01", "label": "Enero"}, ...]
    }
    """
    # Generar rango de años desde 2019 hasta el año actual
    current_year = datetime.now().year
    años = [str(y) for y in range(current_year, 2018, -1)]  # Orden descendente
    
    # Meses con etiquetas
    meses = [
        {'value': '01', 'label': 'Enero'},
        {'value': '02', 'label': 'Febrero'},
        {'value': '03', 'label': 'Marzo'},
        {'value': '04', 'label': 'Abril'},
        {'value': '05', 'label': 'Mayo'},
        {'value': '06', 'label': 'Junio'},
        {'value': '07', 'label': 'Julio'},
        {'value': '08', 'label': 'Agosto'},
        {'value': '09', 'label': 'Septiembre'},
        {'value': '10', 'label': 'Octubre'},
        {'value': '11', 'label': 'Noviembre'},
        {'value': '12', 'label': 'Diciembre'},
    ]
    
    return jsonify({
        'años': años,
        'razones_sociales': RAZONES_SOCIALES_VALIDAS,
        'bancos': BANCOS_VALIDOS,
        'meses': meses
    }), 200

@app.route('/api/search', methods=['POST'])
@jwt_required()  # ← Requiere autenticación
def search():
    """
    Búsqueda de PDFs (protegida)
    Body: {
        "codigo_empleado": "12345",
        "banco": "BBVA",
        "mes": "03",
        "razon_social": "RESGUARDO",
        "año": "2024"
    }
    """
    # DEBUG: Ver qué usuario está haciendo la búsqueda
    user_id = int(get_jwt_identity())  # ← Convertir de string a int
    app.logger.info(f"✓ Búsqueda iniciada por user_id: {user_id}")
    
    filters = request.get_json() or {}
    codigo_empleado = filters.get('codigo_empleado')
    
    # ═══════════════════════════════════════════════════
    # VALIDACIÓN DE INPUT
    # ═══════════════════════════════════════════════════
    if codigo_empleado:
        # Limpiar espacios
        codigo_empleado = str(codigo_empleado).strip()
        
        # Validar formato: solo números, entre 4 y 10 dígitos
        if not re.match(r'^\d{4,10}$', codigo_empleado):
            return jsonify({
                'error': 'Código de empleado inválido. Debe contener entre 4 y 10 dígitos numéricos.',
                'total': 0,
                'results': []
            }), 400
    
    # Validar banco si se proporciona
    if filters.get('banco') and filters['banco'] not in BANCOS_VALIDOS:
        return jsonify({
            'error': f'Banco inválido. Valores permitidos: {BANCOS_VALIDOS}',
            'total': 0,
            'results': []
        }), 400
    
    # Validar mes si se proporciona (01-12)
    if filters.get('mes') and not re.match(r'^(0[1-9]|1[0-2])$', filters['mes']):
        return jsonify({
            'error': 'Mes inválido. Debe ser un valor entre 01 y 12.',
            'total': 0,
            'results': []
        }), 400
    
    # Validar año si se proporciona (formato YYYY, entre 2019 y año actual)
    if filters.get('año'):
        try:
            año_filtro = int(filters['año'])
            current_year = datetime.now().year
            if año_filtro < 2019 or año_filtro > current_year:
                return jsonify({
                    'error': f'Año inválido. Debe ser entre 2019 y {current_year}.',
                    'total': 0,
                    'results': []
                }), 400
        except ValueError:
            return jsonify({
                'error': 'Año inválido. Debe ser un número (ej: 2024).',
                'total': 0,
                'results': []
            }), 400
    
    # Validar razón social si se proporciona
    if filters.get('razon_social') and filters['razon_social'] not in RAZONES_SOCIALES_VALIDAS:
        return jsonify({
            'error': f'Razón social inválida. Valores permitidos: {RAZONES_SOCIALES_VALIDAS}',
            'total': 0,
            'results': []
        }), 400
    
    results = []
    
    try:
        objects = minio_client.list_objects(BUCKET_NAME, recursive=True)
        
        for obj in objects:
            if not obj.object_name.endswith('.pdf'):
                continue
            
            metadata = extract_metadata(obj.object_name)
            
            # Aplicar filtros (incluyendo el nuevo filtro de año)
            if filters.get('año') and metadata['año'] != filters['año']:
                continue
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