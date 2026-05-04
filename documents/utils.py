import re
import unicodedata
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
    'JV RESGUARDO': 'RESGUARDO',
    'RESGUARDO': 'RESGUARDO',
    'J & V RESGUARDO S.A.C.': 'RESGUARDO',
    'J&V RESGUARDO S.A.C.': 'RESGUARDO',
    'JV RESGUARDO S.A.C.': 'RESGUARDO',
    'RESGUARDO S.A.C.': 'RESGUARDO',
    'LIDERMAN ALARMAS':'ALARMAS',
    'LIDERMAN ALARMAS S.A.C.': 'ALARMAS',
    'ALARMAS': 'ALARMAS',
    'ALARMAS S.A.C.': 'ALARMAS',
    'AZZARO': 'AZZARO',
    'AZZARO S.A.C.': 'AZZARO',
    'LIDERMAN FACILITIES': 'FACILITIES',
    'FACILITIES': 'FACILITIES',
    'LIDERMAN SERVICIOS': 'LIDERMAN SERVICIOS',
    'LIDERMAN SERVICIOS S.A.C.': 'LIDERMAN SERVICIOS',
    'LIDERMAN': 'LIDERMAN SERVICIOS',
    'J&V RESGUARDO SELVA': 'SELVA',
    'J & V RESGUARDO SELVA': 'SELVA',
    'SELVA': 'SELVA',
    'SELVA S.A.C.': 'SELVA',
}

RAZONES_SOCIALES_VALIDAS = sorted(set(RAZONES_SOCIALES_MAP.values()))
BANCOS_VALIDOS = ['BBVA', 'BCP', 'INTERBANK', 'SCOTIABANK']

MESES_TOKEN_MAP = {
    'ENERO': '01',
    'ENE': '01',
    'FEBRERO': '02',
    'FEB': '02',
    'MARZO': '03',
    'MAR': '03',
    'ABRIL': '04',
    'ABR': '04',
    'MAYO': '05',
    'MAY': '05',
    'JUNIO': '06',
    'JUN': '06',
    'JULIO': '07',
    'JUL': '07',
    'AGOSTO': '08',
    'AGO': '08',
    'SEPTIEMBRE': '09',
    'SETIEMBRE': '09',
    'SEPT': '09',
    'SET': '09',
    'SEP': '09',
    'OCTUBRE': '10',
    'OCT': '10',
    'NOVIEMBRE': '11',
    'NOV': '11',
    'DICIEMBRE': '12',
    'DIC': '12',
}

MESES_LABEL_MAP = {
    '01': 'ENERO',
    '02': 'FEBRERO',
    '03': 'MARZO',
    '04': 'ABRIL',
    '05': 'MAYO',
    '06': 'JUNIO',
    '07': 'JULIO',
    '08': 'AGOSTO',
    '09': 'SEPTIEMBRE',
    '10': 'OCTUBRE',
    '11': 'NOVIEMBRE',
    '12': 'DICIEMBRE',
}

DEFAULT_COMPANY_PATTERNS = [
    (r'J\s*[&Y]\s*V\s+RESGUARDO\s+SELVA(?:\s+S\.?A\.?C\.?)?', 'SELVA'),
    (r'J\s*&\s*V\s+RESGUARDO(?:\s+S\.?A\.?C\.?)?', 'RESGUARDO'),
    (r'J\s*[&Y]\s*V\s+RESGUARDO(?:\s+S\.?A\.?C\.?)?', 'RESGUARDO'),
    (r'\bJV\s+RESGUARDO(?:\s+S\.?A\.?C\.?)?', 'RESGUARDO'),
    (r'J\s*[&Y]\s*V\s+RESGUARDO', 'RESGUARDO'),
    (r'RESGUARDO\s+S\.?A\.?C\.?', 'RESGUARDO'),
    (r'SELVA\s+S\.?A\.?C\.?', 'SELVA'),
    (r'LIDERMAN\s+FACILITIES', 'FACILITIES'),
    (r'\bFACILITIES\b', 'FACILITIES'),
    (r'LIDERMAN\s+ALARMAS(?:\s+S\.?A\.?C\.?)?', 'ALARMAS'),
    (r'\bALARMAS(?:\s+S\.?A\.?C\.?)?', 'ALARMAS'),
    (r'AZZARO(?:\s+S\.?A\.?C\.?)?', 'AZZARO'),
    (r'LIDERMAN\s+SERVICIOS(?:\s+S\.?A\.?C\.?)?', 'LIDERMAN SERVICIOS'),
    (r'\bLIDERMAN\b(?!\s+FACILITIES)', 'LIDERMAN SERVICIOS'),
]

BANK_PATTERNS = [
    (r'\bBBVA\b', 'BBVA'),
    (r'\bBCP\b', 'BCP'),
    (r'(?<![A-Z0-9])INTER[\s_\-]*BANK(?![A-Z0-9])', 'INTERBANK'),
    (r'(?<![A-Z0-9])SCOTIA[\s_\-]*BANK(?![A-Z0-9])', 'SCOTIABANK'),
]


def _strip_accents(value):
    normalized = unicodedata.normalize('NFKD', str(value or ''))
    return ''.join(ch for ch in normalized if not unicodedata.combining(ch))


def _safe_hint_value(hints, *keys):
    for key in keys:
        if hasattr(hints, 'get'):
            value = hints.get(key)
        else:
            value = hints[key] if isinstance(hints, dict) and key in hints else None
        if value is not None and str(value).strip():
            return str(value).strip()
    return ''


def _normalize_month(value):
    month = str(value or '').strip()
    if not month:
        return ''
    if re.fullmatch(r'0?[1-9]|1[0-2]', month):
        return month.zfill(2)
    return ''


def _extract_year_month_from_text(text):
    text_upper = str(text or '').upper()

    compact_dates = re.findall(r'(?<!\d)(\d{2})(\d{2})(20\d{2})(?!\d)', text_upper)
    if compact_dates:
        _, month, year = compact_dates[0]
        if _normalize_month(month):
            return year, month

    slash_dates = re.findall(r'(?<!\d)(\d{2})[/-](\d{2})[/-](20\d{2})(?!\d)', text_upper)
    if slash_dates:
        # Priorizar fechas que NO sean de nacimiento si es posible
        # Pero esta es una función genérica. La lógica específica va en infer_upload_metadata.
        for dd, month, year in slash_dates:
            if _normalize_month(month):
                # Evitar fechas muy antiguas que podrían ser de nacimiento
                if int(year) > 1990: 
                    return year, month
        
        # Si no hay mejores, devolver la primera
        _, month, year = slash_dates[0]
        return year, month

    year_match = re.search(r'\b(20\d{2})\b', text_upper)
    month_token = _extract_month_token(text_upper)
    if year_match and month_token:
        return year_match.group(1), month_token

    if year_match:
        return year_match.group(1), ''

    return '', ''


def _extract_tregistro_dates(text):
    """
    Especializado para T-Registro: busca Fecha de Inicio o Cese.
    Prioriza estas fechas sobre cualquier otra encontrada en el documento.
    """
    text_upper = _strip_accents(text).upper()
    date_pattern = r'(\d{2})[/-](\d{2})[/-](20\d{2})'

    periodos_match = re.search(
        rf'PERIODOS?\s+DE\s+FORMACION(?P<block>.{{0,1200}})',
        text_upper,
        re.DOTALL,
    )
    if periodos_match:
        block = periodos_match.group('block')
        for label in ('INICIO', 'ALTA', 'BAJA', 'CESE'):
            match = re.search(rf'FECHA\s+(?:DE\s+)?{label}[^\d]{{0,80}}{date_pattern}', block)
            if match:
                _, mes, año = match.groups()
                return año, mes

    labeled_patterns = [
        rf'FECHA\s+DE\s+INICIO\s+DE\s+LA\s+RELACION\s+LABORAL[^\d]{{0,80}}{date_pattern}',
        rf'FECHA\s+(?:DE\s+)?INICIO[^\d]{{0,80}}{date_pattern}',
        rf'FECHA\s+(?:DE\s+)?ALTA[^\d]{{0,80}}{date_pattern}',
        rf'F\.\s*INICIO[^\d]{{0,80}}{date_pattern}',
        rf'FECHA\s+(?:DE\s+)?BAJA[^\d]{{0,80}}{date_pattern}',
        rf'FECHA\s+(?:DE\s+)?CESE[^\d]{{0,80}}{date_pattern}',
        rf'F\.\s*(?:BAJA|CESE)[^\d]{{0,80}}{date_pattern}',
    ]

    for pattern in labeled_patterns:
        match = re.search(pattern, text_upper, re.DOTALL)
        if match:
            _, mes, año = match.groups()
            if int(año) >= 1990:
                return año, mes

    return None, None


def _extract_month_token(text):
    text_upper = str(text or '').upper()
    for token, month in MESES_TOKEN_MAP.items():
        if re.search(rf'\b{re.escape(token)}\b', text_upper):
            return month
    return ''


def _detect_company_from_text(text):
    text_upper = str(text or '').upper()
    for pattern, canonical in DEFAULT_COMPANY_PATTERNS:
        if re.search(pattern, text_upper):
            return canonical

    for known in RAZONES_SOCIALES_VALIDAS:
        if known in text_upper:
            return known

    return ''


def _detect_bank_from_text(text):
    text_upper = _strip_accents(text).upper()
    for pattern, bank in BANK_PATTERNS:
        if re.search(pattern, text_upper):
            return bank
    return ''


def _detect_tipo_documento_from_content(filename, text):
    joined = _strip_accents(f"{filename or ''} {text or ''}").upper()
    tokens = set(re.findall(r'\b\w+\b', joined))

    if 'T-REGISTRO' in joined or 'TREGISTRO' in joined:
        header_text = _get_document_header(text)
        header_upper = header_text.upper()
        if re.search(r'\bBAJA\b', header_upper):
            return 'BAJA'
        if re.search(r'\bALTA\b', header_upper):
            return 'ALTA'
        return 'TREGISTRO'

    if 'SCTR' in joined:
        if 'PENSION' in tokens:
            return 'SCTR PENSION'
        if 'SALUD' in tokens:
            return 'SCTR SALUD'
        return 'SCTR'

    if 'VIDA LEY' in joined:
        return 'VIDA LEY'

    if 'FIN DE MES' in joined:
        return 'FIN DE MES'

    if 'CUADRE' in joined:
        return 'CUADRE'

    if 'PLANILLA' in joined and 'HABER' in joined:
        return 'PLANILLA HABERES'

    return extract_tipo_from_filename(filename)


def _get_document_header(text, max_chars=4000):
    """
    Extrae la cabecera del documento (primeros max_chars caracteres).
    Esto permite detectar ALTA/BAJA en los títulos/encabezados sin falsos
    positivos por historiales de reingresantes en el cuerpo del PDF.
    """
    if not text:
        return ''
    header_cut = text[:max_chars]
    cut_marker = '\n\n\n'
    marker_pos = header_cut.find(cut_marker)
    if marker_pos > 0 and marker_pos < max_chars // 2:
        return header_cut[:marker_pos]
    return header_cut


def infer_upload_metadata(filename, pdf_text=None, hints=None):
    """
    Resuelve metadata para carga automatica usando prioridad de fuentes:
    input usuario > filename/path > contenido PDF.
    """
    hints = hints or {}
    base_meta = extract_metadata(filename)

    text_upper = str(pdf_text or '').upper()
    filename_upper = str(filename or '').upper()

    hint_year = _safe_hint_value(hints, 'año', 'anio', 'year')
    hint_month = _safe_hint_value(hints, 'mes', 'month')
    hint_company = _safe_hint_value(hints, 'razon_social', 'company', 'empresa')
    hint_bank = _safe_hint_value(hints, 'banco', 'bank')
    hint_tipo = _safe_hint_value(hints, 'tipo_documento', 'tipo', 'payroll_type')

    filename_year, filename_month = _extract_year_month_from_text(filename_upper)
    text_year, text_month = _extract_year_month_from_text(text_upper)

    tipo_documento = clean_tipo_documento(hint_tipo) if hint_tipo else ''
    if not tipo_documento:
        tipo_documento = _detect_tipo_documento_from_content(filename_upper, text_upper)

    from docrepo.domain_inference import infer_domain_code
    domain_code = infer_domain_code(f"{filename_upper} {text_upper}", tipo_documento)

    # Lógica especial para T-Registro: prioridad absoluta a Fecha de Inicio/Cese
    if domain_code == 'TREGISTRO':
        treg_year, treg_month = _extract_tregistro_dates(text_upper)
        if treg_year and treg_month:
            text_year, text_month = treg_year, treg_month
        else:
            # Si es T-Registro y no hay fecha clara de inicio/cese, 
            # NO usar fechas genéricas (que podrían ser de nacimiento)
            text_year, text_month = '', ''

    year = hint_year or text_year or filename_year or str(base_meta.get('año') or datetime.now().year)

    month = _normalize_month(hint_month)
    if not month:
        month = _normalize_month(filename_month)
    if not month:
        month = _normalize_month(base_meta.get('mes'))
    if not month:
        month = _normalize_month(text_month)
    if not month:
        month = _extract_month_token(filename_upper) or _extract_month_token(text_upper) or '01'

    company = normalize_razon_social(hint_company) if hint_company else ''
    if not company or company == 'DESCONOCIDO':
        company = normalize_razon_social(base_meta.get('razon_social'))
    if not company or company == 'DESCONOCIDO':
        detected_company = _detect_company_from_text(text_upper)
        company = normalize_razon_social(detected_company) if detected_company else 'DESCONOCIDO'

    bank = (hint_bank or '').upper().strip()
    if bank not in BANCOS_VALIDOS:
        base_bank = (base_meta.get('banco') or '').upper().strip()
        bank = base_bank if base_bank in BANCOS_VALIDOS else ''
    if not bank:
        bank = _detect_bank_from_text(f"{filename_upper} {text_upper}") or 'GENERAL'

    return {
        'año': str(year),
        'mes': str(month).zfill(2),
        'razon_social': company,
        'banco': bank,
        'tipo_documento': tipo_documento,
        'domain_code': domain_code,
    }


def _sanitize_path_segment(value, default_value='GENERAL', max_len=120):
    segment = str(value or '').strip().upper()
    segment = re.sub(r'[<>:"\\|?*\/]+', ' ', segment)
    segment = re.sub(r'\s+', ' ', segment).strip()
    if not segment:
        segment = default_value
    return segment[:max_len]


def build_auto_storage_prefix(metadata, domain_code):
    """
    Genera prefijo logico para almacenamiento automatico.
    """
    year = str(metadata.get('año') or datetime.now().year)
    month = _normalize_month(metadata.get('mes')) or '01'
    month_label = MESES_LABEL_MAP.get(month, 'MES')

    company = _sanitize_path_segment(metadata.get('razon_social'), default_value='DESCONOCIDO', max_len=180)
    tipo = _sanitize_path_segment(metadata.get('tipo_documento'), default_value='GENERAL', max_len=120)

    header_path = f"Planillas {year}/{company}/{month}.{month_label}"
    if domain_code == 'TREGISTRO':
        return f"{header_path}/TREGISTRO/{tipo}"

    if domain_code == 'SEGUROS':
        return f"{header_path}/SEGUROS/{tipo}"

    bank = _sanitize_path_segment(metadata.get('banco'), default_value='GENERAL', max_len=80)
    
    return f"{header_path}/{bank}/{tipo}"


def _extract_text_and_codes_from_pdf_bytes(pdf_bytes):
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


def extract_text_from_pdf_bytes(pdf_bytes):
    """
    Extrae texto y codigos desde bytes de PDF.
    """
    try:
        return _extract_text_and_codes_from_pdf_bytes(pdf_bytes)
    except Exception as e:
        print(f"Error extrayendo texto desde bytes: {e}")
        return None, []

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
        try:
            pdf_bytes = response.read()
        finally:
            response.close()
            response.release_conn()

        return _extract_text_and_codes_from_pdf_bytes(pdf_bytes)
    
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
