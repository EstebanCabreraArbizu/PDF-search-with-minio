import re
import fitz  # PyMuPDF
from datetime import datetime
from django.conf import settings
from minio import Minio
from minio.error import S3Error

# Initialize MinIO client
minio_client = Minio(
    endpoint=settings.MINIO_ENDPOINT.replace('http://', '').replace('https://', ''),
    access_key=settings.MINIO_ACCESS_KEY,
    secret_key=settings.MINIO_SECRET_KEY,
    secure=settings.MINIO_USE_SSL,  # Dynamic SSL configuration
    region=settings.MINIO_REGION      # Optional region for S3
)

# ═══════════════════════════════════════════════════
# CONSTANTES: Mapeo de razones sociales para estandarización
# ═══════════════════════════════════════════════════
RAZONES_SOCIALES_MAP = {
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

RAZONES_SOCIALES_VALIDAS = sorted(set(RAZONES_SOCIALES_MAP.values()))
BANCOS_VALIDOS = ['BBVA', 'BCP', 'INTERBANK', 'SCOTIABANK']

def normalize_razon_social(raw_name):
    """
    Estandariza nombres de razones sociales.
    """
    if not raw_name:
        return 'DESCONOCIDO'
    
    cleaned = re.sub(r'^\d+[\.\s\-]+', '', raw_name.strip())
    cleaned_upper = cleaned.upper().strip()
    
    if cleaned_upper in RAZONES_SOCIALES_MAP:
        return RAZONES_SOCIALES_MAP[cleaned_upper]
    
    for key, standard_name in RAZONES_SOCIALES_MAP.items():
        if key in cleaned_upper or cleaned_upper in key:
            return standard_name
    
    return cleaned_upper

def extract_year_from_path(path_part):
    """
    Extrae el año de carpetas.
    """
    if not path_part:
        return None
    
    range_match = re.search(r'(\d{4})\s*[-–]\s*(\d{4})', path_part)
    if range_match:
        end_year = int(range_match.group(2))
        current_year = datetime.now().year
        return str(min(end_year, current_year))
    
    year_match = re.search(r'(20\d{2})', path_part)
    if year_match:
        return year_match.group(1)
    
    return None

def clean_tipo_documento(name):
    """
    Limpia el nombre de un tipo de documento.
    """
    if not name:
        return 'GENERAL'
    
    name = name.upper().strip()
    name = re.sub(r'[\s_-]*\d{6,8}', '', name)
    name = re.sub(r'\s*\(\d*\)\s*', '', name)
    name = re.sub(r'\s*\(\s*$', '', name)
    name = re.sub(r'[_\s-]+', ' ', name)
    name = name.strip()
    
    if not name:
        return 'GENERAL'
    
    return name

def extract_tipo_from_filename(filename):
    """
    Extrae el tipo de documento del nombre del archivo.
    """
    if not filename:
        return 'GENERAL'
    name = re.sub(r'\.pdf$', '', filename, flags=re.IGNORECASE)
    return clean_tipo_documento(name)

def extract_metadata(file_path):
    """
    Extrae metadata de la ruta jerárquica.
    """
    parts = file_path.split('/')
    año = None
    offset = 0
    
    if len(parts) > 0:
        potential_year = extract_year_from_path(parts[0])
        if potential_year:
            año = potential_year
            offset = 1
    
    if not año:
        año = str(datetime.now().year)
    
    razon_social_raw = parts[offset] if len(parts) > offset else 'DESCONOCIDO'
    razon_social = normalize_razon_social(razon_social_raw)
    
    mes_raw = parts[offset + 1] if len(parts) > offset + 1 else ''
    mes_match = re.search(r'(\d{2})\.', mes_raw)
    mes = mes_match.group(1) if mes_match else '00'
    
    filename = parts[-1] if parts else ''
    banco = 'GENERAL'
    tipo_documento = 'GENERAL'
    
    potential_banco = parts[offset + 2] if len(parts) > offset + 2 else ''
    potential_banco_upper = potential_banco.upper().strip()
    
    is_pdf_file = potential_banco_upper.endswith('.PDF')
    is_valid_banco = potential_banco_upper in BANCOS_VALIDOS
    
    detected_banco_in_name = None
    for banco_valido in BANCOS_VALIDOS:
        if banco_valido in potential_banco_upper:
            detected_banco_in_name = banco_valido
            break
    
    if is_valid_banco:
        banco = potential_banco_upper
        if len(parts) > offset + 3:
            potential_tipo = parts[offset + 3]
            if potential_tipo.upper().endswith('.PDF'):
                tipo_documento = extract_tipo_from_filename(potential_tipo)
            else:
                tipo_documento = clean_tipo_documento(potential_tipo)
        else:
            tipo_documento = extract_tipo_from_filename(filename)
    elif is_pdf_file:
        banco = 'GENERAL'
        tipo_documento = extract_tipo_from_filename(potential_banco)
    elif detected_banco_in_name:
        banco = detected_banco_in_name
        tipo_documento = clean_tipo_documento(potential_banco)
    else:
        for parte in parts:
            parte_upper = parte.upper().strip()
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

def extract_text_from_pdf(object_name):
    """
    Extrae todo el texto de un PDF almacenado en MinIO.
    """
    try:
        response = minio_client.get_object(settings.MINIO_BUCKET, object_name)
        pdf_bytes = response.read()
        
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        texto_completo = ""
        codigos_encontrados = set()
        
        for page in doc:
            text = page.get_text()
            texto_completo += text + "\n"
            codigos = re.findall(r'\b\d{4,10}\b', text)
            codigos_encontrados.update(codigos)
        
        doc.close()
        return texto_completo, list(codigos_encontrados)
    
    except Exception as e:
        print(f"Error extrayendo texto de {object_name}: {e}")
        return None, []

def search_in_pdf(object_name, codigo_empleado):
    """Descarga y busca código en el PDF"""
    try:
        response = minio_client.get_object(settings.MINIO_BUCKET, object_name)
        
        pdf_bytes = response.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        for page_num, page in enumerate(doc):
            text = page.get_text()
            pattern = rf'\b{re.escape(str(codigo_empleado))}\b'
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        return False
    except Exception as e:
        print(f"Error buscando en {object_name}: {e}")
        return False
