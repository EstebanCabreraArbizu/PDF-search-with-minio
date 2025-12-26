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
from pathlib import Path
from models import db, User, DownloadLog, PDFIndex
from dotenv import load_dotenv

# Cargar .env desde el directorio padre del proyecto
env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(env_path)

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
    secure=True  # True en producción con HTTPS
)

# ════════════════════════════════════════════════
# INICIALIZACIÓN: Crear bucket si no existe
# ═══════════════════════════════════════════════════
def init_app():
    """Inicializa base de datos y MinIO"""
    with app.app_context():
        db.create_all()
        
        # Crear índices optimizados para búsqueda
        try:
            # Índice para búsqueda rápida de códigos de empleado
            db.session.execute(db.text("""
                CREATE INDEX IF NOT EXISTS idx_pdf_codigos 
                ON pdf_index 
                USING GIN(to_tsvector('simple', COALESCE(codigos_empleado, '')))
            """))
            
            # Índice compuesto para filtros comunes
            db.session.execute(db.text("""
                CREATE INDEX IF NOT EXISTS idx_pdf_filtros 
                ON pdf_index(año, razon_social, banco, mes)
            """))
            
            db.session.commit()
            app.logger.info("✓ Índices GIN creados para búsqueda full-text")
        except Exception as e:
            app.logger.warning(f"⚠️ No se pudieron crear índices GIN (puede que ya existan): {e}")
            db.session.rollback()

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
    Extrae metadata de la ruta jerárquica con soporte para múltiples estructuras:
    
    ESTRUCTURA COMPLETA (con banco y tipo en carpetas):
    Planillas 2025/RESGUARDO/03.MARZO/BBVA/VACACIONES/planilla.pdf
    → {año: '2025', razon_social: 'RESGUARDO', mes: '03', banco: 'BBVA', tipo_documento: 'VACACIONES'}
    
    ESTRUCTURA CON BANCO (sin carpeta de tipo):
    Planillas 2025/RESGUARDO/03.MARZO/BBVA/REINTEGROS 07102025.pdf
    → {año: '2025', razon_social: 'RESGUARDO', mes: '03', banco: 'BBVA', tipo_documento: 'REINTEGROS'}
    
    ESTRUCTURA SIN BANCO (archivo directo en mes):
    Planillas 2025/LIDERMAN SERVICIOS/10.OCTUBRE/CUADRE SEP 03102025.pdf
    → {año: '2025', razon_social: 'LIDERMAN SERVICIOS', mes: '10', banco: 'GENERAL', tipo_documento: 'CUADRE'}
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
    
    # Extraer nombre del archivo (último elemento)
    filename = parts[-1] if parts else ''
    
    # Determinar banco y tipo de documento basado en la estructura
    banco = 'GENERAL'
    tipo_documento = 'GENERAL'
    
    # Posición esperada del banco: offset + 2
    potential_banco = parts[offset + 2] if len(parts) > offset + 2 else ''
    potential_banco_upper = potential_banco.upper().strip()
    
    # Verificar si potential_banco es un banco válido o un archivo PDF
    is_pdf_file = potential_banco_upper.endswith('.PDF')
    is_valid_banco = potential_banco_upper in BANCOS_VALIDOS
    
    # Buscar si el nombre contiene un banco válido (ej: "CTS BBVA" contiene "BBVA")
    detected_banco_in_name = None
    for banco_valido in BANCOS_VALIDOS:
        if banco_valido in potential_banco_upper:
            detected_banco_in_name = banco_valido
            break
    
    if is_valid_banco:
        # Estructura con banco: Planillas 2025/RAZON/MES/BANCO/...
        banco = potential_banco_upper
        
        # El tipo de documento puede estar en la siguiente carpeta o en el nombre del archivo
        if len(parts) > offset + 3:
            potential_tipo = parts[offset + 3]
            if potential_tipo.upper().endswith('.PDF'):
                # El archivo está directamente en la carpeta del banco
                tipo_documento = extract_tipo_from_filename(potential_tipo)
            else:
                # Hay carpeta de tipo de documento - limpiar números finales
                tipo_documento = clean_tipo_documento(potential_tipo)
        else:
            tipo_documento = extract_tipo_from_filename(filename)
    elif is_pdf_file:
        # Estructura sin banco: archivo directamente en carpeta de mes
        # Planillas 2025/RAZON/MES/ARCHIVO.pdf
        banco = 'GENERAL'
        tipo_documento = extract_tipo_from_filename(potential_banco)
    elif detected_banco_in_name:
        # La carpeta contiene el nombre del banco (ej: "CTS BBVA" contiene "BBVA")
        banco = detected_banco_in_name
        # El nombre de la carpeta es el tipo de documento - limpiar números finales
        tipo_documento = clean_tipo_documento(potential_banco)
    else:
        # Puede ser una subcarpeta antes del archivo, buscar banco en todo el path
        for parte in parts:
            parte_upper = parte.upper().strip()
            # Buscar banco exacto o contenido en el nombre
            if parte_upper in BANCOS_VALIDOS:
                banco = parte_upper
                break
            for banco_valido in BANCOS_VALIDOS:
                if banco_valido in parte_upper:
                    banco = banco_valido
                    break
            if banco != 'GENERAL':
                break
        tipo_documento = extract_tipo_from_filename(filename)
    
    return {
        'año': año,
        'razon_social': razon_social,
        'mes': mes,
        'banco': banco,
        'tipo_documento': tipo_documento,
    }


def clean_tipo_documento(name):
    """
    Limpia el nombre de un tipo de documento (de carpeta o archivo).
    Remueve fechas numéricas (6-8 dígitos) en cualquier posición.
    
    Ejemplos:
    - "CTS NOV 2024 SOLES - II_15052025" → "CTS NOV 2024 SOLES - II"
    - "FIN DE MES DEST_27062025" → "FIN DE MES DEST"
    - "GRATI DEST_12122025 CONSOLIDADO" → "GRATI DEST CONSOLIDADO"
    - "011025 REINTEGROS 631." → "REINTEGROS 631."
    - "INTERES LEGAL_02042025 BBVA" → "INTERES LEGAL BBVA"
    - "VACACIONES" → "VACACIONES"
    """
    if not name:
        return 'GENERAL'
    
    name = name.upper().strip()
    
    # Remover fechas de 6-8 dígitos en CUALQUIER posición (con separador opcional)
    # Esto captura: _15052025, 07102025, _12122025, 02042025, etc.
    name = re.sub(r'[\s_-]*\d{6,8}', '', name)
    
    # Remover posibles (1), (2) o paréntesis sueltos
    name = re.sub(r'\s*\(\d*\)\s*', '', name)  # (1), (2), ()
    name = re.sub(r'\s*\(\s*$', '', name)       # Paréntesis abierto al final
    
    # Remover guiones bajos, espacios y guiones duplicados
    name = re.sub(r'[_\s-]+', ' ', name)  # Reemplazar múltiples separadores por espacio
    name = name.strip()
    
    if not name:
        return 'GENERAL'
    
    return name


def extract_tipo_from_filename(filename):
    """
    Extrae el tipo de documento del nombre del archivo.
    Remueve la extensión .pdf y cualquier dato numérico al final (fechas).
    
    Ejemplos:
    - "REINTEGROS 07102025.pdf" → "REINTEGROS"
    - "CUADRE SEP 03102025.pdf" → "CUADRE SEP"
    - "LIQUIDACIONES DESTACADOS 02122025.PDF" → "LIQUIDACIONES DESTACADOS"
    - "VACACIONES DESTACADOS_18122025.PDF" → "VACACIONES DESTACADOS"
    - "CTS NOV 14112025.PDF" → "CTS NOV"
    - "FM DESTACADOS 25072025.PDF" → "FM DESTACADOS"
    - "FIN DE MES DEST_27062025.PDF" → "FIN DE MES DEST"
    - "GRATI DEST_12122025" → "GRATI DEST"
    - "CUADRE MAYO_0306205" → "CUADRE MAYO"
    """
    if not filename:
        return 'GENERAL'
    
    # Remover extensión .pdf
    name = re.sub(r'\.pdf$', '', filename, flags=re.IGNORECASE)
    
    # Usar la función de limpieza común
    return clean_tipo_documento(name)


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
    Combina opciones estáticas con datos reales del índice.
    
    Response: {
        "años": ["2024", "2023", "2022", ...],
        "razones_sociales": ["ALARMAS", "FACILITIES", ...],
        "bancos": ["BBVA", "BCP", ...],
        "meses": [{"value": "01", "label": "Enero"}, ...],
        "index_stats": {"total": 1500, "indexed": true}
    }
    """
    from sqlalchemy import func
    
    # Meses con etiquetas (estático)
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
    
    # Intentar obtener opciones dinámicas del índice
    try:
        total_indexed = PDFIndex.query.count()
        
        if total_indexed > 0:
            # Años reales del índice (ordenados descendente)
            años_db = db.session.query(PDFIndex.año)\
                .distinct()\
                .filter(PDFIndex.año.isnot(None))\
                .order_by(PDFIndex.año.desc())\
                .all()
            años = [a[0] for a in años_db if a[0]]
            
            # Razones sociales reales del índice
            razones_db = db.session.query(PDFIndex.razon_social)\
                .distinct()\
                .filter(PDFIndex.razon_social.isnot(None))\
                .order_by(PDFIndex.razon_social)\
                .all()
            razones_sociales = [r[0] for r in razones_db if r[0]]
            
            # Bancos reales del índice
            bancos_db = db.session.query(PDFIndex.banco)\
                .distinct()\
                .filter(PDFIndex.banco.isnot(None))\
                .order_by(PDFIndex.banco)\
                .all()
            bancos = [b[0] for b in bancos_db if b[0]]
            
            # Tipos de documento reales del índice
            tipos_db = db.session.query(PDFIndex.tipo_documento)\
                .distinct()\
                .filter(PDFIndex.tipo_documento.isnot(None))\
                .order_by(PDFIndex.tipo_documento)\
                .all()
            tipos_documento = [t[0] for t in tipos_db if t[0]]
            
            return jsonify({
                'años': años,
                'razones_sociales': razones_sociales,
                'bancos': bancos,
                'tipos_documento': tipos_documento,
                'meses': meses,
                'index_stats': {
                    'total': total_indexed,
                    'indexed': True,
                    'source': 'postgresql_index'
                }
            }), 200
    
    except Exception as e:
        app.logger.warning(f"⚠️ No se pudo leer índice, usando valores estáticos: {e}")
    
    # Fallback: usar valores estáticos
    current_year = datetime.now().year
    años = [str(y) for y in range(current_year, 2018, -1)]
    
    return jsonify({
        'años': años,
        'razones_sociales': RAZONES_SOCIALES_VALIDAS,
        'bancos': BANCOS_VALIDOS + ['GENERAL'],  # Incluir GENERAL para archivos sin banco específico
        'meses': meses,
        'index_stats': {
            'total': 0,
            'indexed': False,
            'source': 'static_config'
        }
    }), 200

@app.route('/api/search', methods=['POST'])
@jwt_required()  # ← Requiere autenticación
def search():
    """
    Búsqueda de PDFs (protegida) - OPTIMIZADA CON ÍNDICE PostgreSQL
    
    Body: {
        "codigo_empleado": "12345",
        "banco": "BBVA",
        "mes": "03",
        "razon_social": "RESGUARDO",
        "año": "2024",
        "use_index": true  // opcional, default true
    }
    
    Si use_index=true (default): Busca en PostgreSQL (rápido, ~20ms)
    Si use_index=false: Busca en MinIO directamente (lento, legacy)
    """
    import time
    start_time = time.time()
    
    # DEBUG: Ver qué usuario está haciendo la búsqueda
    user_id = int(get_jwt_identity())  # ← Convertir de string a int
    app.logger.info(f"✓ Búsqueda iniciada por user_id: {user_id}")
    
    filters = request.get_json() or {}
    codigo_empleado = filters.get('codigo_empleado')
    use_index = filters.get('use_index', True)  # Por defecto usa índice
    
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
    
    # Validar banco si se proporciona (BANCOS_VALIDOS + 'GENERAL')
    if filters.get('banco') and filters['banco'] not in BANCOS_VALIDOS + ['GENERAL']:
        return jsonify({
            'error': f'Banco inválido. Valores permitidos: {BANCOS_VALIDOS + ["GENERAL"]}',
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
    
    # ═══════════════════════════════════════════════════
    # VALIDACIÓN: Código de empleado es OBLIGATORIO
    # ═══════════════════════════════════════════════════
    # Sin código de empleado, la búsqueda retornaría demasiados resultados
    # y no tendría sentido para el caso de uso (buscar planillas de un empleado)
    if not codigo_empleado:
        return jsonify({
            'error': 'El código de empleado es obligatorio para realizar la búsqueda.',
            'hint': 'Los filtros adicionales (banco, mes, año, razon_social) son opcionales y ayudan a reducir resultados.',
            'total': 0,
            'results': []
        }), 400
    
    # ═══════════════════════════════════════════════════
    # BÚSQUEDA CON ÍNDICE (PostgreSQL) - RÁPIDA
    # ═══════════════════════════════════════════════════
    if use_index:
        try:
            # Construir query dinámico
            query = PDFIndex.query.filter(PDFIndex.is_indexed == True)
            
            # Aplicar filtros
            if filters.get('año'):
                query = query.filter(PDFIndex.año == filters['año'])
            if filters.get('banco'):
                query = query.filter(PDFIndex.banco == filters['banco'])
            if filters.get('mes'):
                query = query.filter(PDFIndex.mes == filters['mes'])
            if filters.get('razon_social'):
                query = query.filter(PDFIndex.razon_social == filters['razon_social'])
            if filters.get('tipo_documento'):
                # Búsqueda parcial (ILIKE) para encontrar tipos similares
                query = query.filter(PDFIndex.tipo_documento.ilike(f"%{filters['tipo_documento']}%"))
            
            # Búsqueda por código de empleado (en campo indexado)
            if codigo_empleado:
                # Buscar en el campo codigos_empleado (contiene códigos separados por coma)
                query = query.filter(PDFIndex.codigos_empleado.contains(codigo_empleado))
            
            # Ejecutar query
            pdfs = query.limit(500).all()  # Límite de seguridad
            
            results = [pdf.to_dict() for pdf in pdfs]
            
            elapsed = round((time.time() - start_time) * 1000, 2)  # ms
            app.logger.info(f"✓ Búsqueda indexada: {len(results)} resultados en {elapsed}ms")
            
            return jsonify({
                'total': len(results),
                'results': results,
                'search_time_ms': elapsed,
                'source': 'postgresql_index'
            })
            
        except Exception as e:
            app.logger.warning(f"⚠️ Error en búsqueda indexada, fallback a MinIO: {e}")
            # Si falla el índice, hacer fallback a búsqueda directa
            use_index = False
    
    # ═══════════════════════════════════════════════════
    # BÚSQUEDA DIRECTA (MinIO) - LEGACY/FALLBACK
    # ═══════════════════════════════════════════════════
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
    
    elapsed = round((time.time() - start_time) * 1000, 2)
    app.logger.info(f"✓ Búsqueda MinIO: {len(results)} resultados en {elapsed}ms")
    
    return jsonify({
        'total': len(results),
        'results': results,
        'search_time_ms': elapsed,
        'source': 'minio_direct'
    })

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


# ═══════════════════════════════════════════════════
# INDEXACIÓN DE PDFs (PostgreSQL)
# ═══════════════════════════════════════════════════
def extract_text_from_pdf(object_name):
    """
    Extrae todo el texto de un PDF almacenado en MinIO.
    También extrae códigos de empleado encontrados.
    
    Returns:
        tuple: (texto_completo, codigos_empleado_lista)
    """
    try:
        response = minio_client.get_object(BUCKET_NAME, object_name)
        pdf_bytes = response.read()
        
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        texto_completo = ""
        codigos_encontrados = set()
        
        for page in doc:
            text = page.get_text()
            texto_completo += text + "\n"
            
            # Buscar patrones de códigos de empleado (4-10 dígitos)
            # Ajustar el patrón según el formato real de tus códigos
            codigos = re.findall(r'\b\d{4,10}\b', text)
            codigos_encontrados.update(codigos)
        
        doc.close()
        return texto_completo, list(codigos_encontrados)
    
    except Exception as e:
        app.logger.error(f"Error extrayendo texto de {object_name}: {e}")
        return None, []


def index_single_pdf(obj):
    """
    Indexa un solo PDF de MinIO en PostgreSQL.
    
    Args:
        obj: Objeto MinIO con .object_name, .size, .last_modified
        
    Returns:
        PDFIndex: Registro creado o actualizado
    """
    # Verificar si ya existe
    existing = PDFIndex.query.filter_by(minio_object_name=obj.object_name).first()
    
    # Si existe y no ha cambiado, saltar
    if existing and existing.last_modified == obj.last_modified:
        return existing
    
    # Extraer metadata de la ruta
    metadata = extract_metadata(obj.object_name)
    
    # Extraer texto del PDF (puede ser lento)
    texto, codigos = extract_text_from_pdf(obj.object_name)
    
    if existing:
        # Actualizar registro existente
        existing.razon_social = metadata['razon_social']
        existing.banco = metadata['banco']
        existing.mes = metadata['mes']
        existing.año = metadata['año']
        existing.tipo_documento = metadata['tipo_documento']
        existing.size_bytes = obj.size
        existing.codigos_empleado = ','.join(codigos) if codigos else None
        existing.last_modified = obj.last_modified
        existing.indexed_at = datetime.utcnow()
        existing.is_indexed = texto is not None
        existing.index_error = None if texto else "Error extrayendo texto"
        return existing
    else:
        # Crear nuevo registro
        pdf_index = PDFIndex(
            minio_object_name=obj.object_name,
            razon_social=metadata['razon_social'],
            banco=metadata['banco'],
            mes=metadata['mes'],
            año=metadata['año'],
            tipo_documento=metadata['tipo_documento'],
            size_bytes=obj.size,
            codigos_empleado=','.join(codigos) if codigos else None,
            last_modified=obj.last_modified,
            is_indexed=texto is not None,
            index_error=None if texto else "Error extrayendo texto"
        )
        db.session.add(pdf_index)
        return pdf_index


@app.route('/api/reindex', methods=['POST'])
@jwt_required()
def reindex_all():
    """
    Reindexar todos los PDFs de MinIO en PostgreSQL.
    Solo admin puede ejecutar esto.
    
    INCLUYE: Eliminación de índices huérfanos (PDFs eliminados de MinIO)
    
    Body (opcional): {
        "clean_orphans": true  // default: true - elimina índices de PDFs eliminados
    }
    
    Response: {
        "message": "Indexación completada",
        "total_indexed": 150,
        "new_indexed": 50,
        "updated": 10,
        "orphans_removed": 5,
        "errors": 3,
        "time_seconds": 45.2
    }
    """
    from flask_jwt_extended import get_jwt
    import time
    
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({'error': 'Permiso denegado. Solo admin puede reindexar.'}), 403
    
    # silent=True evita errores si el body está vacío
    data = request.get_json(silent=True) or {}
    clean_orphans = data.get('clean_orphans', True)
    
    start_time = time.time()
    indexed_count = 0
    new_count = 0
    updated_count = 0
    error_count = 0
    orphans_removed = 0
    
    try:
        # Obtener lista de todos los PDFs en MinIO
        minio_objects = {}
        objects = minio_client.list_objects(BUCKET_NAME, recursive=True)
        
        for obj in objects:
            if obj.object_name.endswith('.pdf'):
                minio_objects[obj.object_name] = obj
        
        app.logger.info(f"📁 Encontrados {len(minio_objects)} PDFs en MinIO")
        
        # ═══════════════════════════════════════════════════
        # PASO 1: Eliminar índices huérfanos (si está habilitado)
        # ═══════════════════════════════════════════════════
        if clean_orphans:
            # Obtener todos los object_names indexados
            indexed_names = set(
                row[0] for row in 
                db.session.query(PDFIndex.minio_object_name).all()
            )
            
            # Encontrar huérfanos (indexados pero no en MinIO)
            orphan_names = indexed_names - set(minio_objects.keys())
            
            if orphan_names:
                PDFIndex.query.filter(
                    PDFIndex.minio_object_name.in_(orphan_names)
                ).delete(synchronize_session=False)
                orphans_removed = len(orphan_names)
                db.session.commit()
                app.logger.info(f"🗑️ Eliminados {orphans_removed} índices huérfanos")
        
        # ═══════════════════════════════════════════════════
        # PASO 2: Indexar PDFs nuevos o actualizados
        # ═══════════════════════════════════════════════════
        for object_name, obj in minio_objects.items():
            try:
                existing = PDFIndex.query.filter_by(minio_object_name=object_name).first()
                
                # Si existe y no ha cambiado, saltar
                if existing and existing.last_modified == obj.last_modified:
                    indexed_count += 1
                    continue
                
                # Indexar (nuevo o actualizado)
                index_single_pdf(obj)
                indexed_count += 1
                
                if existing:
                    updated_count += 1
                else:
                    new_count += 1
                
                # Commit cada 50 documentos
                if indexed_count % 50 == 0:
                    db.session.commit()
                    app.logger.info(f"✓ Procesados {indexed_count} PDFs...")
                    
            except Exception as e:
                error_count += 1
                app.logger.error(f"✗ Error indexando {object_name}: {e}")
        
        # Commit final
        db.session.commit()
        
        elapsed = round(time.time() - start_time, 2)
        app.logger.info(f"✓ Indexación completada: {indexed_count} PDFs en {elapsed}s")
        
        return jsonify({
            'message': 'Indexación completada',
            'total_in_minio': len(minio_objects),
            'total_indexed': indexed_count,
            'new_indexed': new_count,
            'updated': updated_count,
            'orphans_removed': orphans_removed,
            'errors': error_count,
            'time_seconds': elapsed
        }), 200
        
    except S3Error as e:
        return jsonify({'error': f'Error de MinIO: {str(e)}'}), 500
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error inesperado: {str(e)}'}), 500


@app.route('/api/index/sync', methods=['POST'])
@jwt_required()
def sync_index():
    """
    Sincronización RÁPIDA del índice.
    Solo procesa cambios (nuevos, eliminados) sin re-extraer texto de PDFs existentes.
    
    Mucho más rápido que /api/reindex para uso frecuente.
    
    Response: {
        "new_files": 5,
        "removed_orphans": 2,
        "time_seconds": 1.2
    }
    """
    from flask_jwt_extended import get_jwt
    import time
    
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({'error': 'Permiso denegado. Solo admin puede sincronizar.'}), 403
    
    start_time = time.time()
    new_files = 0
    removed_orphans = 0
    
    try:
        # Obtener lista de MinIO (solo nombres y metadata básica)
        minio_names = set()
        minio_objects = {}
        
        for obj in minio_client.list_objects(BUCKET_NAME, recursive=True):
            if obj.object_name.endswith('.pdf'):
                minio_names.add(obj.object_name)
                minio_objects[obj.object_name] = obj
        
        # Obtener lista de indexados
        indexed_names = set(
            row[0] for row in 
            db.session.query(PDFIndex.minio_object_name).all()
        )
        
        # Encontrar nuevos (en MinIO pero no indexados)
        new_names = minio_names - indexed_names
        
        # Encontrar huérfanos (indexados pero no en MinIO)
        orphan_names = indexed_names - minio_names
        
        # Eliminar huérfanos
        if orphan_names:
            PDFIndex.query.filter(
                PDFIndex.minio_object_name.in_(orphan_names)
            ).delete(synchronize_session=False)
            removed_orphans = len(orphan_names)
        
        # Indexar nuevos
        for name in new_names:
            try:
                index_single_pdf(minio_objects[name])
                new_files += 1
            except Exception as e:
                app.logger.error(f"✗ Error indexando {name}: {e}")
        
        db.session.commit()
        
        elapsed = round(time.time() - start_time, 2)
        
        return jsonify({
            'message': 'Sincronización completada',
            'total_in_minio': len(minio_names),
            'total_indexed': len(indexed_names) - removed_orphans + new_files,
            'new_files': new_files,
            'removed_orphans': removed_orphans,
            'time_seconds': elapsed
        }), 200
        
    except S3Error as e:
        return jsonify({'error': f'Error de MinIO: {str(e)}'}), 500
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error inesperado: {str(e)}'}), 500


@app.route('/api/index/stats', methods=['GET'])
@jwt_required()
def get_index_stats():
    """
    Estadísticas del índice de PDFs.
    
    Response: {
        "total_indexed": 1500,
        "total_size_gb": 45.2,
        "by_year": {"2024": 500, "2023": 400, ...},
        "by_razon_social": {"RESGUARDO": 300, ...},
        "last_indexed": "2024-12-19T10:30:00"
    }
    """
    from sqlalchemy import func
    
    total = PDFIndex.query.count()
    total_size = db.session.query(func.sum(PDFIndex.size_bytes)).scalar() or 0
    
    # Agrupar por año
    by_year = dict(
        db.session.query(PDFIndex.año, func.count(PDFIndex.id))
        .group_by(PDFIndex.año)
        .all()
    )
    
    # Agrupar por razón social
    by_razon = dict(
        db.session.query(PDFIndex.razon_social, func.count(PDFIndex.id))
        .group_by(PDFIndex.razon_social)
        .all()
    )
    
    # Último indexado
    last = PDFIndex.query.order_by(PDFIndex.indexed_at.desc()).first()
    
    return jsonify({
        'total_indexed': total,
        'total_size_gb': round(total_size / (1024**3), 2),
        'by_year': by_year,
        'by_razon_social': by_razon,
        'by_banco': dict(
            db.session.query(PDFIndex.banco, func.count(PDFIndex.id))
            .group_by(PDFIndex.banco)
            .all()
        ),
        'last_indexed': last.indexed_at.isoformat() if last else None,
        'indexed_successfully': PDFIndex.query.filter_by(is_indexed=True).count(),
        'with_errors': PDFIndex.query.filter_by(is_indexed=False).count()
    }), 200


# ═══════════════════════════════════════════════════
# GESTIÓN DE ARCHIVOS - ESTILO GOOGLE DRIVE
# ═══════════════════════════════════════════════════

@app.route('/api/files/list', methods=['GET'])
@jwt_required()
def list_files():
    """
    Listar PDFs indexados desde PostgreSQL (mucho más rápido que MinIO).
    
    Query params:
        folder: Filtrar por carpeta (ej: "Planillas 2025/")
        search: Buscar por nombre de archivo
        año: Filtrar por año
        mes: Filtrar por mes
        banco: Filtrar por banco
        razon_social: Filtrar por razón social
        page: Página (default: 1)
        per_page: Resultados por página (default: 100)
        sort: Campo de ordenamiento (default: "indexed_at")
        order: Orden asc/desc (default: "desc")
    
    Response: {
        "files": [...],
        "total": 5234,
        "page": 1,
        "per_page": 100,
        "total_pages": 53
    }
    """
    # Parámetros de filtrado
    folder_filter = request.args.get('folder', '').strip()
    search_query = request.args.get('search', '').strip()
    año = request.args.get('año', '').strip()
    mes = request.args.get('mes', '').strip()
    banco = request.args.get('banco', '').strip()
    razon_social = request.args.get('razon_social', '').strip()
    tipo_documento = request.args.get('tipo_documento', '').strip()
    
    # Parámetros de paginación y ordenamiento
    page = int(request.args.get('page', 1))
    per_page = min(int(request.args.get('per_page', 100)), 500)  # Máximo 500 por página
    sort_field = request.args.get('sort', 'indexed_at')
    order = request.args.get('order', 'desc')
    
    try:
        # Construir query con filtros
        query = PDFIndex.query.filter_by(is_indexed=True)
        
        # Filtro por carpeta (buscar en el path)
        if folder_filter:
            query = query.filter(PDFIndex.minio_object_name.like(f"{folder_filter}%"))
        
        # Búsqueda por nombre de archivo
        if search_query:
            query = query.filter(PDFIndex.minio_object_name.ilike(f"%{search_query}%"))
        
        # Filtros de metadatos
        if año:
            query = query.filter_by(año=año)
        if mes:
            query = query.filter_by(mes=mes)
        if banco:
            query = query.filter_by(banco=banco)
        if razon_social:
            query = query.filter_by(razon_social=razon_social)
        if tipo_documento:
            # Búsqueda parcial (ILIKE) para tipos similares
            query = query.filter(PDFIndex.tipo_documento.ilike(f"%{tipo_documento}%"))
        
        # Ordenamiento
        if sort_field == 'indexed_at':
            order_by = PDFIndex.indexed_at.desc() if order == 'desc' else PDFIndex.indexed_at.asc()
        elif sort_field == 'last_modified':
            order_by = PDFIndex.last_modified.desc() if order == 'desc' else PDFIndex.last_modified.asc()
        elif sort_field == 'size':
            order_by = PDFIndex.size_bytes.desc() if order == 'desc' else PDFIndex.size_bytes.asc()
        elif sort_field == 'filename':
            order_by = PDFIndex.minio_object_name.asc() if order == 'asc' else PDFIndex.minio_object_name.desc()
        else:
            order_by = PDFIndex.indexed_at.desc()
        
        query = query.order_by(order_by)
        
        # Contar total antes de paginar
        total = query.count()
        
        # Aplicar paginación
        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        
        # Construir respuesta
        files = []
        for record in paginated.items:
            # Calcular tamaño legible
            size_bytes = record.size_bytes or 0
            if size_bytes < 1024:
                size_human = f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                size_human = f"{size_bytes / 1024:.1f} KB"
            else:
                size_human = f"{size_bytes / (1024 * 1024):.1f} MB"
            
            # Extraer nombre y carpeta
            parts = record.minio_object_name.split('/')
            file_name = parts[-1]
            folder_name = '/'.join(parts[:-1]) if len(parts) > 1 else ''
            
            files.append({
                'name': file_name,
                'path': record.minio_object_name,
                'folder': folder_name,
                'size_bytes': size_bytes,
                'size_human': size_human,
                'last_modified': record.last_modified.isoformat() if record.last_modified else None,
                'indexed_at': record.indexed_at.isoformat() if record.indexed_at else None,
                'indexed': record.is_indexed,
                'año': record.año,
                'mes': record.mes,
                'banco': record.banco,
                'razon_social': record.razon_social,
                'tipo_documento': record.tipo_documento,
                'download_url': f'/api/download/{record.minio_object_name}'
            })
        
        return jsonify({
            'files': files,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': paginated.pages,
            'has_next': paginated.has_next,
            'has_prev': paginated.has_prev
        }), 200
        
    except Exception as e:
        app.logger.error(f"✗ Error listando archivos: {e}")
        return jsonify({'error': f'Error al listar archivos: {str(e)}'}), 500


# ═══════════════════════════════════════════════════
# LISTAR CARPETAS (para selector de ubicación) - OPTIMIZADO CON POSTGRESQL
# ═══════════════════════════════════════════════════
@app.route('/api/folders', methods=['GET'])
@jwt_required()
def list_folders():
    """
    Lista carpetas disponibles usando el índice de PostgreSQL (INSTANTÁNEO).
    Extrae las carpetas únicas del campo minio_object_name.
    
    Query params:
        parent: Carpeta padre para listar (opcional, default: raíz)
    
    Response: {
        "folders": [
            {"name": "Planillas 2025", "path": "Planillas 2025/", "count": 150},
            {"name": "RESGUARDO", "path": "Planillas 2025/RESGUARDO/", "count": 50}
        ],
        "current_path": "",
        "breadcrumb": []
    }
    """
    from sqlalchemy import func, distinct
    import time
    
    start_time = time.time()
    parent = request.args.get('parent', '').strip()
    
    # Normalizar parent (asegurar que termine en / si no está vacío)
    if parent and not parent.endswith('/'):
        parent += '/'
    
    try:
        # Obtener todos los paths únicos que empiezan con el parent
        if parent:
            # Buscar paths que empiezan con el parent
            paths_query = db.session.query(
                PDFIndex.minio_object_name
            ).filter(
                PDFIndex.minio_object_name.like(f'{parent}%')
            ).all()
        else:
            # Todos los paths
            paths_query = db.session.query(
                PDFIndex.minio_object_name
            ).all()
        
        # Extraer carpetas únicas del nivel actual
        folders = {}
        parent_depth = len(parent.rstrip('/').split('/')) if parent else 0
        
        for (path,) in paths_query:
            # Obtener la parte relativa al parent
            relative_path = path[len(parent):] if parent else path
            parts = relative_path.split('/')
            
            # Si hay al menos 2 partes (carpeta + archivo), hay una subcarpeta
            if len(parts) > 1:
                folder_name = parts[0]
                folder_path = parent + folder_name + '/'
                
                if folder_path not in folders:
                    folders[folder_path] = {
                        'name': folder_name,
                        'path': folder_path,
                        'is_folder': True,
                        'count': 0
                    }
                folders[folder_path]['count'] += 1
        
        # Construir breadcrumb
        breadcrumb = []
        if parent:
            parts = parent.rstrip('/').split('/')
            accumulated = ''
            for part in parts:
                accumulated += part + '/'
                breadcrumb.append({
                    'name': part,
                    'path': accumulated
                })
        
        elapsed = round((time.time() - start_time) * 1000, 2)
        app.logger.info(f"✓ Carpetas listadas en {elapsed}ms: {len(folders)} carpetas en '{parent}'")
        
        return jsonify({
            'folders': sorted(folders.values(), key=lambda x: x['name'].lower()),
            'current_path': parent,
            'breadcrumb': breadcrumb,
            'parent_path': '/'.join(parent.rstrip('/').split('/')[:-1]) + '/' if parent and '/' in parent.rstrip('/') else '',
            'time_ms': elapsed
        }), 200
        
    except Exception as e:
        app.logger.error(f"✗ Error listando carpetas: {e}")
        return jsonify({'error': f'Error al listar carpetas: {str(e)}'}), 500


@app.route('/api/files/upload', methods=['POST'])
@jwt_required()
def upload_file():
    """
    Subir uno o varios PDFs a MinIO y auto-indexarlos.
    
    Multipart form-data:
        files[]: Uno o más archivos PDF
        folder: Carpeta destino (opcional, ej: "Planillas 2025/")
    
    Response: {
        "success": true,
        "uploaded": [
            {
                "filename": "archivo.pdf",
                "path": "Planillas 2025/archivo.pdf",
                "size": 123456,
                "indexed": true
            }
        ],
        "errors": [],
        "total_uploaded": 5,
        "total_indexed": 5,
        "total_errors": 0
    }
    """
    from flask_jwt_extended import get_jwt
    
    # Verificar permisos (solo admin puede subir)
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({'error': 'Solo administradores pueden subir archivos.'}), 403
    
    # Obtener archivos y carpeta destino
    files = request.files.getlist('files[]')
    folder = request.form.get('folder', '').strip()
    
    if not files:
        return jsonify({'error': 'No se proporcionaron archivos.'}), 400
    
    uploaded = []
    errors = []
    
    for file in files:
        if not file or file.filename == '':
            continue
            
        # Validar extensión
        if not file.filename.lower().endswith('.pdf'):
            errors.append({
                'filename': file.filename,
                'error': 'Solo se permiten archivos PDF'
            })
            continue
        
        try:
            # Construir ruta en MinIO
            if folder and not folder.endswith('/'):
                folder += '/'
            
            object_name = f"{folder}{file.filename}" if folder else file.filename
            
            # Subir a MinIO
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)
            
            minio_client.put_object(
                BUCKET_NAME,
                object_name,
                file,
                length=file_size,
                content_type='application/pdf'
            )
            
            app.logger.info(f"✓ Archivo subido: {object_name}")
            
            # Auto-indexar
            indexed = False
            try:
                # Obtener objeto recién subido
                obj = minio_client.stat_object(BUCKET_NAME, object_name)
                index_single_pdf(obj)
                db.session.commit()
                indexed = True
                app.logger.info(f"✓ Archivo indexado: {object_name}")
            except Exception as idx_error:
                app.logger.error(f"✗ Error indexando {object_name}: {idx_error}")
            
            uploaded.append({
                'filename': file.filename,
                'path': object_name,
                'size': file_size,
                'indexed': indexed
            })
            
        except Exception as e:
            app.logger.error(f"✗ Error subiendo {file.filename}: {e}")
            errors.append({
                'filename': file.filename,
                'error': str(e)
            })
    
    return jsonify({
        'success': len(uploaded) > 0,
        'uploaded': uploaded,
        'errors': errors,
        'total_uploaded': len(uploaded),
        'total_indexed': sum(1 for u in uploaded if u['indexed']),
        'total_errors': len(errors)
    }), 200 if len(uploaded) > 0 else 400


@app.route('/api/files/delete', methods=['DELETE'])
@jwt_required()
def delete_file():
    """
    Eliminar un archivo de MinIO y su índice en PostgreSQL.
    
    JSON body: {
        "path": "Planillas 2025/archivo.pdf"
    }
    
    Response: {
        "success": true,
        "message": "Archivo eliminado correctamente",
        "path": "Planillas 2025/archivo.pdf"
    }
    """
    from flask_jwt_extended import get_jwt
    
    # Verificar permisos
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({'error': 'Solo administradores pueden eliminar archivos.'}), 403
    
    data = request.get_json(silent=True) or {}
    file_path = data.get('path', '').strip()
    
    if not file_path:
        return jsonify({'error': 'Debe proporcionar la ruta del archivo.'}), 400
    
    try:
        # Eliminar de MinIO
        minio_client.remove_object(BUCKET_NAME, file_path)
        app.logger.info(f"✓ Archivo eliminado de MinIO: {file_path}")
        
        # Eliminar índice de PostgreSQL
        PDFIndex.query.filter_by(minio_object_name=file_path).delete()
        db.session.commit()
        app.logger.info(f"✓ Índice eliminado de PostgreSQL: {file_path}")
        
        return jsonify({
            'success': True,
            'message': 'Archivo eliminado correctamente',
            'path': file_path
        }), 200
        
    except S3Error as e:
        if e.code == 'NoSuchKey':
            # El archivo no existe en MinIO, pero intentar limpiar el índice
            PDFIndex.query.filter_by(minio_object_name=file_path).delete()
            db.session.commit()
            return jsonify({'error': 'El archivo no existe en MinIO.'}), 404
        else:
            app.logger.error(f"✗ Error S3 eliminando {file_path}: {e}")
            return jsonify({'error': f'Error en MinIO: {str(e)}'}), 500
    except Exception as e:
        app.logger.error(f"✗ Error eliminando {file_path}: {e}")
        return jsonify({'error': f'Error al eliminar: {str(e)}'}), 500


# ═══════════════════════════════════════════════════
# BÚSQUEDA MASIVA POR CÓDIGOS DE EMPLEADO / DNI
# ═══════════════════════════════════════════════════
@app.route('/api/search/bulk', methods=['POST'])
@jwt_required()
def bulk_search():
    """
    Búsqueda masiva por múltiples códigos de empleado o DNI.
    
    JSON body: {
        "codigos": "12345678, 87654321, 11223344" o ["12345678", "87654321"],
        "año": "2025",
        "mes": "03",
        "banco": "BCP",
        "razon_social": "RESGUARDO"
    }
    
    Response: {
        "total": 15,
        "codigos_encontrados": ["12345678", "87654321"],
        "codigos_no_encontrados": ["11223344"],
        "results": [...],
        "can_merge": true
    }
    """
    from sqlalchemy import or_
    
    data = request.get_json(silent=True) or {}
    codigos_input = data.get('codigos', [])
    
    # Limpiar y validar códigos
    if isinstance(codigos_input, str):
        # Separar por comas, espacios, o nuevas líneas
        codigos = [c.strip() for c in re.split(r'[,\s\n]+', codigos_input) if c.strip()]
    else:
        codigos = [str(c).strip() for c in codigos_input if str(c).strip()]
    
    # Eliminar duplicados manteniendo orden
    codigos = list(dict.fromkeys(codigos))
    
    if not codigos:
        return jsonify({
            'error': 'Debe proporcionar al menos un código de empleado o DNI.',
            'total': 0,
            'results': []
        }), 400
    
    if len(codigos) > 500:
        return jsonify({
            'error': 'Máximo 500 códigos por búsqueda.',
            'total': 0,
            'results': []
        }), 400
    
    # Filtros adicionales
    año = data.get('año', '').strip()
    mes = data.get('mes', '').strip()
    banco = data.get('banco', '').strip()
    razon_social = data.get('razon_social', '').strip()
    tipo_documento = data.get('tipo_documento', '').strip()
    
    try:
        # Construir query base con filtros
        query = PDFIndex.query.filter(PDFIndex.is_indexed == True)
        
        # Aplicar filtros adicionales primero (reduce el dataset)
        if año:
            query = query.filter(PDFIndex.año == año)
        if mes:
            query = query.filter(PDFIndex.mes == mes)
        if banco:
            query = query.filter(PDFIndex.banco == banco)
        if razon_social:
            query = query.filter(PDFIndex.razon_social == razon_social)
        if tipo_documento:
            # Búsqueda parcial (ILIKE) para encontrar tipos similares
            query = query.filter(PDFIndex.tipo_documento.ilike(f"%{tipo_documento}%"))
        
        # Construir condiciones OR para todos los códigos en UNA sola consulta
        # Usando ILIKE para cada código
        codigo_conditions = [
            PDFIndex.codigos_empleado.ilike(f'%{codigo}%') 
            for codigo in codigos
        ]
        
        # Aplicar OR de todos los códigos
        query = query.filter(or_(*codigo_conditions))
        
        # Ejecutar consulta una sola vez
        all_records = query.all()
        
        app.logger.info(f"Búsqueda masiva: {len(codigos)} códigos → {len(all_records)} registros encontrados")
        
        # Procesar resultados y determinar qué códigos se encontraron
        results = []
        codigos_encontrados = set()
        
        for record in all_records:
            # Determinar qué códigos de la búsqueda están en este PDF
            codigos_en_pdf = record.codigos_empleado or ''
            codigos_match = []
            
            for codigo in codigos:
                # Verificar si el código está en los códigos del empleado
                if codigo.lower() in codigos_en_pdf.lower():
                    codigos_match.append(codigo)
                    codigos_encontrados.add(codigo)
            
            if codigos_match:  # Solo añadir si al menos un código coincide
                results.append({
                    'id': record.id,
                    'filename': record.minio_object_name,
                    'metadata': {
                        'año': record.año,
                        'mes': record.mes,
                        'banco': record.banco,
                        'razon_social': record.razon_social,
                        'tipo_documento': record.tipo_documento
                    },
                    'size_bytes': record.size_bytes or 0,
                    'size_kb': round((record.size_bytes or 0) / 1024, 1),
                    'download_url': f'/api/download/{record.minio_object_name}',
                    'codigos_match': codigos_match
                })
        
        # Códigos no encontrados
        codigos_no_encontrados = [c for c in codigos if c not in codigos_encontrados]
        
        # Ordenar resultados por año, mes, filename
        results.sort(key=lambda x: (
            x['metadata'].get('año', ''), 
            x['metadata'].get('mes', ''), 
            x['filename']
        ))
        
        app.logger.info(f"Resultado: {len(codigos_encontrados)} códigos encontrados, {len(codigos_no_encontrados)} no encontrados")
        
        return jsonify({
            'total': len(results),
            'codigos_buscados': codigos,
            'codigos_encontrados': list(codigos_encontrados),
            'codigos_no_encontrados': codigos_no_encontrados,
            'results': results,
            'can_merge': len(results) > 1
        }), 200
        
    except Exception as e:
        app.logger.error(f"✗ Error en búsqueda masiva: {e}")
        import traceback
        app.logger.error(traceback.format_exc())
        return jsonify({
            'error': f'Error en la búsqueda: {str(e)}',
            'total': 0,
            'results': []
        }), 500


# ═══════════════════════════════════════════════════
# FUSIONAR MÚLTIPLES PDFs EN UNO SOLO
# ═══════════════════════════════════════════════════
@app.route('/api/merge-pdfs', methods=['POST'])
@jwt_required()
def merge_pdfs():
    """
    Combina múltiples PDFs en un único archivo para descargar.
    
    JSON body: {
        "paths": [
            "Planillas 2025/archivo1.pdf",
            "Planillas 2025/archivo2.pdf"
        ],
        "output_name": "documentos_combinados"  (opcional)
    }
    
    Response: PDF file (application/pdf)
    """
    from io import BytesIO
    
    data = request.get_json(silent=True) or {}
    paths = data.get('paths', [])
    output_name = data.get('output_name', 'documentos_combinados').strip()
    
    if not paths or len(paths) < 1:
        return jsonify({'error': 'Debe proporcionar al menos un archivo PDF.'}), 400
    
    if len(paths) > 100:
        return jsonify({'error': 'Máximo 100 archivos por fusión.'}), 400
    
    try:
        # Crear documento PDF combinado
        merged_pdf = fitz.open()
        files_merged = []
        errors = []
        
        for path in paths:
            try:
                # Descargar PDF de MinIO
                response = minio_client.get_object(BUCKET_NAME, path)
                pdf_bytes = response.read()
                response.close()
                response.release_conn()
                
                # Abrir y añadir al documento combinado
                src_pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
                merged_pdf.insert_pdf(src_pdf)
                src_pdf.close()
                
                files_merged.append(path)
                app.logger.info(f"✓ Añadido al merge: {path}")
                
            except S3Error as e:
                app.logger.error(f"✗ Error descargando {path}: {e}")
                errors.append({'path': path, 'error': str(e)})
            except Exception as e:
                app.logger.error(f"✗ Error procesando {path}: {e}")
                errors.append({'path': path, 'error': str(e)})
        
        if not files_merged:
            return jsonify({
                'error': 'No se pudo procesar ningún archivo.',
                'errors': errors
            }), 400
        
        # Exportar PDF combinado a bytes
        output = BytesIO()
        merged_pdf.save(output)
        merged_pdf.close()
        output.seek(0)
        
        # Sanitizar nombre de archivo
        safe_name = re.sub(r'[^\w\s\-]', '', output_name)[:50]
        if not safe_name:
            safe_name = 'documentos_combinados'
        
        # Registrar descarga
        current_user_id = get_jwt_identity()
        log_entry = DownloadLog(
            user_id=current_user_id,
            filename=f"MERGED:{len(files_merged)}_archivos_{safe_name}.pdf",
            ip_address=request.remote_addr
        )
        db.session.add(log_entry)
        db.session.commit()
        
        app.logger.info(f"✓ PDF combinado generado: {len(files_merged)} archivos, {len(errors)} errores")
        
        return Response(
            output.read(),
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="{safe_name}.pdf"',
                'X-Files-Merged': str(len(files_merged)),
                'X-Merge-Errors': str(len(errors))
            }
        )
        
    except Exception as e:
        app.logger.error(f"✗ Error fusionando PDFs: {e}")
        return jsonify({'error': f'Error al fusionar PDFs: {str(e)}'}), 500


if __name__ == '__main__':
    init_app()
    # Con JWT_SECRET_KEY fijo en docker-compose, ya no hay problema con hot-reload
    app.run(host='0.0.0.0', port=5000, debug=True)

@app.route('/api/files/upload', methods=['POST'])
@jwt_required()
def upload_file():
    """
    Subir uno o varios PDFs a MinIO y auto-indexarlos.
    
    Multipart form-data:
        files[]: Uno o más archivos PDF
        folder: Carpeta destino (opcional, ej: "Planillas 2025/")
    
    Response: {
        "success": true,
        "uploaded": [
            {
                "filename": "archivo.pdf",
                "path": "Planillas 2025/archivo.pdf",
                "size": 123456,
                "indexed": true
            }
        ],
        "errors": [],
        "total_uploaded": 5,
        "total_indexed": 5,
        "total_errors": 0
    }
    """
    from flask_jwt_extended import get_jwt
    
    # Verificar permisos (solo admin puede subir)
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({'error': 'Solo administradores pueden subir archivos.'}), 403
    
    # Obtener archivos y carpeta destino
    files = request.files.getlist('files[]')
    folder = request.form.get('folder', '').strip()
    
    if not files:
        return jsonify({'error': 'No se proporcionaron archivos.'}), 400
    
    uploaded = []
    errors = []
    
    for file in files:
        if not file or file.filename == '':
            continue
            
        # Validar extensión
        if not file.filename.lower().endswith('.pdf'):
            errors.append({
                'filename': file.filename,
                'error': 'Solo se permiten archivos PDF'
            })
            continue
        
        try:
            # Construir ruta en MinIO
            if folder and not folder.endswith('/'):
                folder += '/'
            
            object_name = f"{folder}{file.filename}" if folder else file.filename
            
            # Subir a MinIO
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)
            
            minio_client.put_object(
                BUCKET_NAME,
                object_name,
                file,
                length=file_size,
                content_type='application/pdf'
            )
            
            app.logger.info(f"✓ Archivo subido: {object_name}")
            
            # Auto-indexar
            indexed = False
            try:
                # Obtener objeto recién subido
                obj = minio_client.stat_object(BUCKET_NAME, object_name)
                index_single_pdf(obj)
                db.session.commit()
                indexed = True
                app.logger.info(f"✓ Archivo indexado: {object_name}")
            except Exception as idx_error:
                app.logger.error(f"✗ Error indexando {object_name}: {idx_error}")
            
            uploaded.append({
                'filename': file.filename,
                'path': object_name,
                'size': file_size,
                'indexed': indexed
            })
            
        except Exception as e:
            app.logger.error(f"✗ Error subiendo {file.filename}: {e}")
            errors.append({
                'filename': file.filename,
                'error': str(e)
            })
    
    return jsonify({
        'success': len(uploaded) > 0,
        'uploaded': uploaded,
        'errors': errors,
        'total_uploaded': len(uploaded),
        'total_indexed': sum(1 for u in uploaded if u['indexed']),
        'total_errors': len(errors)
    }), 200 if len(uploaded) > 0 else 400


@app.route('/api/files/delete', methods=['DELETE'])
@jwt_required()
def delete_file():
    """
    Eliminar un archivo de MinIO y su índice en PostgreSQL.
    
    JSON body: {
        "path": "Planillas 2025/archivo.pdf"
    }
    
    Response: {
        "success": true,
        "message": "Archivo eliminado correctamente",
        "path": "Planillas 2025/archivo.pdf"
    }
    """
    from flask_jwt_extended import get_jwt
    
    # Verificar permisos
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({'error': 'Solo administradores pueden eliminar archivos.'}), 403
    
    data = request.get_json(silent=True) or {}
    file_path = data.get('path', '').strip()
    
    if not file_path:
        return jsonify({'error': 'Debe proporcionar la ruta del archivo.'}), 400
    
    try:
        # Eliminar de MinIO
        minio_client.remove_object(BUCKET_NAME, file_path)
        app.logger.info(f"✓ Archivo eliminado de MinIO: {file_path}")
        
        # Eliminar índice de PostgreSQL
        PDFIndex.query.filter_by(minio_object_name=file_path).delete()
        db.session.commit()
        app.logger.info(f"✓ Índice eliminado de PostgreSQL: {file_path}")
        
        return jsonify({
            'success': True,
            'message': 'Archivo eliminado correctamente',
            'path': file_path
        }), 200
        
    except S3Error as e:
        if e.code == 'NoSuchKey':
            # El archivo no existe en MinIO, pero intentar limpiar el índice
            PDFIndex.query.filter_by(minio_object_name=file_path).delete()
            db.session.commit()
            return jsonify({'error': 'El archivo no existe en MinIO.'}), 404
        else:
            app.logger.error(f"✗ Error S3 eliminando {file_path}: {e}")
            return jsonify({'error': f'Error en MinIO: {str(e)}'}), 500
    except Exception as e:
        app.logger.error(f"✗ Error eliminando {file_path}: {e}")
        return jsonify({'error': f'Error al eliminar: {str(e)}'}), 500


# ═══════════════════════════════════════════════════
# BÚSQUEDA MASIVA POR CÓDIGOS DE EMPLEADO / DNI
# ═══════════════════════════════════════════════════
@app.route('/api/search/bulk', methods=['POST'])
@jwt_required()
def bulk_search():
    """
    Búsqueda masiva por múltiples códigos de empleado o DNI.
    
    JSON body: {
        "codigos": "12345678, 87654321, 11223344" o ["12345678", "87654321"],
        "año": "2025",
        "mes": "03",
        "banco": "BCP",
        "razon_social": "RESGUARDO"
    }
    
    Response: {
        "total": 15,
        "codigos_encontrados": ["12345678", "87654321"],
        "codigos_no_encontrados": ["11223344"],
        "results": [...],
        "can_merge": true
    }
    """
    from sqlalchemy import or_
    
    data = request.get_json(silent=True) or {}
    codigos_input = data.get('codigos', [])
    
    # Limpiar y validar códigos
    if isinstance(codigos_input, str):
        # Separar por comas, espacios, o nuevas líneas
        codigos = [c.strip() for c in re.split(r'[,\s\n]+', codigos_input) if c.strip()]
    else:
        codigos = [str(c).strip() for c in codigos_input if str(c).strip()]
    
    # Eliminar duplicados manteniendo orden
    codigos = list(dict.fromkeys(codigos))
    
    if not codigos:
        return jsonify({
            'error': 'Debe proporcionar al menos un código de empleado o DNI.',
            'total': 0,
            'results': []
        }), 400
    
    if len(codigos) > 500:
        return jsonify({
            'error': 'Máximo 500 códigos por búsqueda.',
            'total': 0,
            'results': []
        }), 400
    
    # Filtros adicionales
    año = data.get('año', '').strip()
    mes = data.get('mes', '').strip()
    banco = data.get('banco', '').strip()
    razon_social = data.get('razon_social', '').strip()
    tipo_documento = data.get('tipo_documento', '').strip()
    
    try:
        # Construir query base con filtros
        query = PDFIndex.query.filter(PDFIndex.is_indexed == True)
        
        # Aplicar filtros adicionales primero (reduce el dataset)
        if año:
            query = query.filter(PDFIndex.año == año)
        if mes:
            query = query.filter(PDFIndex.mes == mes)
        if banco:
            query = query.filter(PDFIndex.banco == banco)
        if razon_social:
            query = query.filter(PDFIndex.razon_social == razon_social)
        if tipo_documento:
            # Búsqueda parcial (ILIKE) para encontrar tipos similares
            query = query.filter(PDFIndex.tipo_documento.ilike(f"%{tipo_documento}%"))
        
        # Construir condiciones OR para todos los códigos en UNA sola consulta
        # Usando ILIKE para cada código
        codigo_conditions = [
            PDFIndex.codigos_empleado.ilike(f'%{codigo}%') 
            for codigo in codigos
        ]
        
        # Aplicar OR de todos los códigos
        query = query.filter(or_(*codigo_conditions))
        
        # Ejecutar consulta una sola vez
        all_records = query.all()
        
        app.logger.info(f"Búsqueda masiva: {len(codigos)} códigos → {len(all_records)} registros encontrados")
        
        # Procesar resultados y determinar qué códigos se encontraron
        results = []
        codigos_encontrados = set()
        
        for record in all_records:
            # Determinar qué códigos de la búsqueda están en este PDF
            codigos_en_pdf = record.codigos_empleado or ''
            codigos_match = []
            
            for codigo in codigos:
                # Verificar si el código está en los códigos del empleado
                if codigo.lower() in codigos_en_pdf.lower():
                    codigos_match.append(codigo)
                    codigos_encontrados.add(codigo)
            
            if codigos_match:  # Solo añadir si al menos un código coincide
                results.append({
                    'id': record.id,
                    'filename': record.minio_object_name,
                    'metadata': {
                        'año': record.año,
                        'mes': record.mes,
                        'banco': record.banco,
                        'razon_social': record.razon_social,
                        'tipo_documento': record.tipo_documento
                    },
                    'size_bytes': record.size_bytes or 0,
                    'size_kb': round((record.size_bytes or 0) / 1024, 1),
                    'download_url': f'/api/download/{record.minio_object_name}',
                    'codigos_match': codigos_match
                })
        
        # Códigos no encontrados
        codigos_no_encontrados = [c for c in codigos if c not in codigos_encontrados]
        
        # Ordenar resultados por año, mes, filename
        results.sort(key=lambda x: (
            x['metadata'].get('año', ''), 
            x['metadata'].get('mes', ''), 
            x['filename']
        ))
        
        app.logger.info(f"Resultado: {len(codigos_encontrados)} códigos encontrados, {len(codigos_no_encontrados)} no encontrados")
        
        return jsonify({
            'total': len(results),
            'codigos_buscados': codigos,
            'codigos_encontrados': list(codigos_encontrados),
            'codigos_no_encontrados': codigos_no_encontrados,
            'results': results,
            'can_merge': len(results) > 1
        }), 200
        
    except Exception as e:
        app.logger.error(f"✗ Error en búsqueda masiva: {e}")
        import traceback
        app.logger.error(traceback.format_exc())
        return jsonify({
            'error': f'Error en la búsqueda: {str(e)}',
            'total': 0,
            'results': []
        }), 500


# ═══════════════════════════════════════════════════
# FUSIONAR MÚLTIPLES PDFs EN UNO SOLO
# ═══════════════════════════════════════════════════
@app.route('/api/merge-pdfs', methods=['POST'])
@jwt_required()
def merge_pdfs():
    """
    Combina múltiples PDFs en un único archivo para descargar.
    
    JSON body: {
        "paths": [
            "Planillas 2025/archivo1.pdf",
            "Planillas 2025/archivo2.pdf"
        ],
        "output_name": "documentos_combinados"  (opcional)
    }
    
    Response: PDF file (application/pdf)
    """
    from io import BytesIO
    
    data = request.get_json(silent=True) or {}
    paths = data.get('paths', [])
    output_name = data.get('output_name', 'documentos_combinados').strip()
    
    if not paths or len(paths) < 1:
        return jsonify({'error': 'Debe proporcionar al menos un archivo PDF.'}), 400
    
    if len(paths) > 100:
        return jsonify({'error': 'Máximo 100 archivos por fusión.'}), 400
    
    try:
        # Crear documento PDF combinado
        merged_pdf = fitz.open()
        files_merged = []
        errors = []
        
        for path in paths:
            try:
                # Descargar PDF de MinIO
                response = minio_client.get_object(BUCKET_NAME, path)
                pdf_bytes = response.read()
                response.close()
                response.release_conn()
                
                # Abrir y añadir al documento combinado
                src_pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
                merged_pdf.insert_pdf(src_pdf)
                src_pdf.close()
                
                files_merged.append(path)
                app.logger.info(f"✓ Añadido al merge: {path}")
                
            except S3Error as e:
                app.logger.error(f"✗ Error descargando {path}: {e}")
                errors.append({'path': path, 'error': str(e)})
            except Exception as e:
                app.logger.error(f"✗ Error procesando {path}: {e}")
                errors.append({'path': path, 'error': str(e)})
        
        if not files_merged:
            return jsonify({
                'error': 'No se pudo procesar ningún archivo.',
                'errors': errors
            }), 400
        
        # Exportar PDF combinado a bytes
        output = BytesIO()
        merged_pdf.save(output)
        merged_pdf.close()
        output.seek(0)
        
        # Sanitizar nombre de archivo
        safe_name = re.sub(r'[^\w\s\-]', '', output_name)[:50]
        if not safe_name:
            safe_name = 'documentos_combinados'
        
        # Registrar descarga
        current_user_id = get_jwt_identity()
        log_entry = DownloadLog(
            user_id=current_user_id,
            filename=f"MERGED:{len(files_merged)}_archivos_{safe_name}.pdf",
            ip_address=request.remote_addr
        )
        db.session.add(log_entry)
        db.session.commit()
        
        app.logger.info(f"✓ PDF combinado generado: {len(files_merged)} archivos, {len(errors)} errores")
        
        return Response(
            output.read(),
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="{safe_name}.pdf"',
                'X-Files-Merged': str(len(files_merged)),
                'X-Merge-Errors': str(len(errors))
            }
        )
        
    except Exception as e:
        app.logger.error(f"✗ Error fusionando PDFs: {e}")
        return jsonify({'error': f'Error al fusionar PDFs: {str(e)}'}), 500


if __name__ == '__main__':
    init_app()
    # Con JWT_SECRET_KEY fijo en docker-compose, ya no hay problema con hot-reload
    app.run(host='0.0.0.0', port=5000, debug=True)