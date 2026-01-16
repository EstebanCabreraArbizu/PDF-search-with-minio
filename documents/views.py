from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework import status
from django.db.models import Q
from .models import PDFIndex, DownloadLog
from .serializers import PDFIndexSerializer
from .storage import download_pdf

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
        
        pdf_bytes = download_pdf(object_name)
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

class SearchView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        import time
        start_time = time.time()

        codigo = request.data.get('codigo_empleado', '')
        use_index = request.data.get('use_index', True)
        año = request.data.get('año')
        mes = request.data.get('mes')
        
        if codigo is not " ":
            codigo = str(codigo).strip()
            if not re.match(r'^\d{6}$', codigo):
                return Response({'error': 'El código debe tener exactamente 6 dígitos'}, status=400)
        if filters
        query = Q(codigos_empleado__icontains=codigo)
        if año:
            query &= Q(año=año)
        if mes:
            query &= Q(mes=mes)
        
        results = PDFIndex.objects.filter(query)[:100]
        serializer = PDFIndexSerializer(results, many=True)
        return Response({'total': len(results), 'results': serializer.data})

class ReindexView(APIView):
    permission_classes = [IsAdminUser]  # Solo admins

    def post(self, request):
        # Tu lógica de reindexación aquí
        return Response({'success': True, 'message': 'Reindexación iniciada'})