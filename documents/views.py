from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework import status
from django.db.models import Q, Sum, Count
from django.http import StreamingHttpResponse
from .models import PDFIndex, DownloadLog
from .serializers import PDFIndexSerializer
from .utils import (
    minio_client, extract_metadata, search_in_pdf, 
    extract_text_from_pdf, BANCOS_VALIDOS, RAZONES_SOCIALES_VALIDAS
)
import time
from datetime import datetime
import re
from django.conf import settings
import concurrent.futures

# Cache simple en memoria para listado de MinIO (como en Flask app)
_minio_list_cache = {'time': 0, 'data': None}

from django.shortcuts import render
from django.db import connection


# ═══════════════════════════════════════════════════
# UTILITY VIEWS (Auth/Health)
# ═══════════════════════════════════════════════════

class CurrentUserView(APIView):
    """
    Obtiene información del usuario actual.
    GET /api/me
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user
        return Response({
            'id': user.id,
            'username': user.username,
            'role': 'admin' if user.is_staff else 'user',
            'is_active': user.is_active
        })


class HealthCheckView(APIView):
    """
    Health check para monitoreo (PostgreSQL + MinIO).
    GET /health
    """
    permission_classes = []  # Sin autenticación
    
    def get(self, request):
        from datetime import datetime
        
        # Verificar PostgreSQL
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
            db_status = 'ok'
        except Exception as e:
            db_status = f'error: {str(e)}'
        
        # Verificar MinIO
        try:
            minio_client.bucket_exists(settings.MINIO_BUCKET)
            minio_status = 'ok'
        except Exception as e:
            minio_status = f'error: {str(e)}'
        
        overall_status = 'ok' if db_status == 'ok' and minio_status == 'ok' else 'degraded'
        
        return Response({
            'status': overall_status,
            'timestamp': datetime.utcnow().isoformat(),
            'services': {
                'database': db_status,
                'storage': minio_status
            }
        }, status=200 if overall_status == 'ok' else 503)

from django.db import connection


# ═══════════════════════════════════════════════════
# UTILITY VIEWS (Auth/Health)
# ═══════════════════════════════════════════════════

class CurrentUserView(APIView):
    """
    Obtiene información del usuario actual.
    GET /api/me
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user
        return Response({
            'id': user.id,
            'username': user.username,
            'role': 'admin' if user.is_staff else 'user',
            'is_active': user.is_active
        })


class HealthCheckView(APIView):
    """
    Health check para monitoreo (PostgreSQL + MinIO).
    GET /health
    """
    permission_classes = []  # Sin autenticación
    
    def get(self, request):
        from datetime import datetime
        
        # Verificar PostgreSQL
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
            db_status = 'ok'
        except Exception as e:
            db_status = f'error: {str(e)}'
        
        # Verificar MinIO
        try:
            minio_client.bucket_exists(settings.MINIO_BUCKET)
            minio_status = 'ok'
        except Exception as e:
            minio_status = f'error: {str(e)}'
        
        overall_status = 'ok' if db_status == 'ok' and minio_status == 'ok' else 'degraded'
        
        return Response({
            'status': overall_status,
            'timestamp': datetime.utcnow().isoformat(),
            'services': {
                'database': db_status,
                'storage': minio_status
            }
        }, status=200 if overall_status == 'ok' else 503)


def index(request):
    return render(request, 'documents/search.html')

class FilterOptionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        meses = [
            {'value': '01', 'label': 'Enero'}, {'value': '02', 'label': 'Febrero'},
            {'value': '03', 'label': 'Marzo'}, {'value': '04', 'label': 'Abril'},
            {'value': '05', 'label': 'Mayo'}, {'value': '06', 'label': 'Junio'},
            {'value': '07', 'label': 'Julio'}, {'value': '08', 'label': 'Agosto'},
            {'value': '09', 'label': 'Septiembre'}, {'value': '10', 'label': 'Octubre'},
            {'value': '11', 'label': 'Noviembre'}, {'value': '12', 'label': 'Diciembre'},
        ]
        
        try:
            total_indexed = PDFIndex.objects.count()
            if total_indexed > 0:
                años = list(PDFIndex.objects.values_list('año', flat=True).distinct().order_by('-año'))
                razones = list(PDFIndex.objects.values_list('razon_social', flat=True).distinct().order_by('razon_social'))
                bancos = list(PDFIndex.objects.values_list('banco', flat=True).distinct().order_by('banco'))
                tipos = list(PDFIndex.objects.values_list('tipo_documento', flat=True).distinct().order_by('tipo_documento'))
                
                return Response({
                    'años': [a for a in años if a],
                    'razones_sociales': [r for r in razones if r],
                    'bancos': [b for b in bancos if b],
                    'tipos_documento': [t for t in tipos if t],
                    'meses': meses,
                    'index_stats': {'total': total_indexed, 'indexed': True, 'source': 'postgresql_index'},
                    'index_stats': {'total': total_indexed, 'indexed': True, 'source': 'postgresql_index'}
                })
        except Exception as e:
            pass
            
        return Response({
            'años': [str(y) for y in range(datetime.now().year, 2018, -1)],
            'razones_sociales': RAZONES_SOCIALES_VALIDAS,
            'bancos': BANCOS_VALIDOS + ['GENERAL'],
            'meses': meses,
            'index_stats': {'total': 0, 'indexed': False, 'source': 'static_config'},
            'index_stats': {'total': 0, 'indexed': False, 'source': 'static_config'}
        })

class SearchView(APIView):
    """
    Búsqueda de PDFs con validaciones completas.
    POST /api/search
    """
    """
    Búsqueda de PDFs con validaciones completas.
    POST /api/search
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from datetime import datetime
        from datetime import datetime
        start_time = time.time()
        data = request.data
        codigo_empleado = str(data.get('codigo_empleado', '')).strip()
        use_index = data.get('use_index', True)
        
        # ═══════════════════════════════════════════════════
        # VALIDACIONES COMPLETAS
        # ═══════════════════════════════════════════════════
        
        # Validar código de empleado (obligatorio)
        # ═══════════════════════════════════════════════════
        # VALIDACIONES COMPLETAS
        # ═══════════════════════════════════════════════════
        
        # Validar código de empleado (obligatorio)
        if not codigo_empleado:
            return Response({
                'error': 'El código de empleado es obligatorio para realizar la búsqueda.',
                'hint': 'Los filtros adicionales (banco, mes, año, razon_social) son opcionales.',
                'total': 0, 'results': []
            }, status=400)
            return Response({
                'error': 'El código de empleado es obligatorio para realizar la búsqueda.',
                'hint': 'Los filtros adicionales (banco, mes, año, razon_social) son opcionales.',
                'total': 0, 'results': []
            }, status=400)
            
        if not re.match(r'^\d{4,10}$', codigo_empleado):
            return Response({
                'error': 'Código de empleado inválido. Debe contener entre 4 y 10 dígitos numéricos.',
                'total': 0, 'results': []
            }, status=400)
        
        # Validar banco
        if data.get('banco') and data['banco'] not in BANCOS_VALIDOS + ['GENERAL']:
            return Response({
                'error': f'Banco inválido. Valores permitidos: {BANCOS_VALIDOS + ["GENERAL"]}',
                'total': 0, 'results': []
            }, status=400)
        
        # Validar mes (01-12)
        if data.get('mes') and not re.match(r'^(0[1-9]|1[0-2])$', str(data['mes'])):
            return Response({
                'error': 'Mes inválido. Debe ser un valor entre 01 y 12.',
                'total': 0, 'results': []
            }, status=400)
        
        # Validar año (2019 - actual)
        if data.get('año'):
            try:
                año_filtro = int(data['año'])
                current_year = datetime.now().year
                if año_filtro < 2019 or año_filtro > current_year:
                    return Response({
                        'error': f'Año inválido. Debe ser entre 2019 y {current_year}.',
                        'total': 0, 'results': []
                    }, status=400)
            except ValueError:
                return Response({
                    'error': 'Año inválido. Debe ser un número (ej: 2024).',
                    'total': 0, 'results': []
                }, status=400)
        
        # Validar razón social
        if data.get('razon_social') and data['razon_social'] not in RAZONES_SOCIALES_VALIDAS:
            return Response({
                'error': f'Razón social inválida. Valores permitidos: {RAZONES_SOCIALES_VALIDAS}',
                'total': 0, 'results': []
            }, status=400)

        # ═══════════════════════════════════════════════════
        # BÚSQUEDA INDEXADA (PostgreSQL)
        # ═══════════════════════════════════════════════════
            return Response({
                'error': 'Código de empleado inválido. Debe contener entre 4 y 10 dígitos numéricos.',
                'total': 0, 'results': []
            }, status=400)
        
        # Validar banco
        if data.get('banco') and data['banco'] not in BANCOS_VALIDOS + ['GENERAL']:
            return Response({
                'error': f'Banco inválido. Valores permitidos: {BANCOS_VALIDOS + ["GENERAL"]}',
                'total': 0, 'results': []
            }, status=400)
        
        # Validar mes (01-12)
        if data.get('mes') and not re.match(r'^(0[1-9]|1[0-2])$', str(data['mes'])):
            return Response({
                'error': 'Mes inválido. Debe ser un valor entre 01 y 12.',
                'total': 0, 'results': []
            }, status=400)
        
        # Validar año (2019 - actual)
        if data.get('año'):
            try:
                año_filtro = int(data['año'])
                current_year = datetime.now().year
                if año_filtro < 2019 or año_filtro > current_year:
                    return Response({
                        'error': f'Año inválido. Debe ser entre 2019 y {current_year}.',
                        'total': 0, 'results': []
                    }, status=400)
            except ValueError:
                return Response({
                    'error': 'Año inválido. Debe ser un número (ej: 2024).',
                    'total': 0, 'results': []
                }, status=400)
        
        # Validar razón social
        if data.get('razon_social') and data['razon_social'] not in RAZONES_SOCIALES_VALIDAS:
            return Response({
                'error': f'Razón social inválida. Valores permitidos: {RAZONES_SOCIALES_VALIDAS}',
                'total': 0, 'results': []
            }, status=400)

        # ═══════════════════════════════════════════════════
        # BÚSQUEDA INDEXADA (PostgreSQL)
        # ═══════════════════════════════════════════════════
        if use_index:
            try:
                query = Q(is_indexed=True)
                if data.get('año'): query &= Q(año=data['año'])
                if data.get('banco'): query &= Q(banco=data['banco'])
                if data.get('mes'): query &= Q(mes=data['mes'])
                if data.get('razon_social'): query &= Q(razon_social=data['razon_social'])
                if data.get('tipo_documento'): query &= Q(tipo_documento__icontains=data['tipo_documento'])
                
                query &= Q(codigos_empleado__contains=codigo_empleado)
                
                results = PDFIndex.objects.filter(query)[:500]
                serializer = PDFIndexSerializer(results, many=True)
                
                elapsed = round((time.time() - start_time) * 1000, 2)
                return Response({
                    'total': len(results),
                    'results': serializer.data,
                    'search_time_ms': elapsed,
                    'source': 'postgresql_index'
                })
            except Exception as e:
                # Fallback to MinIO search (legacy)
                # Fallback to MinIO search (legacy)
                pass

        # ═══════════════════════════════════════════════════
        # FALLBACK: Búsqueda Directa MinIO (Legacy)
        # ═══════════════════════════════════════════════════
        # ═══════════════════════════════════════════════════
        # FALLBACK: Búsqueda Directa MinIO (Legacy)
        # ═══════════════════════════════════════════════════
        results = []
        try:
            objects = minio_client.list_objects(settings.MINIO_BUCKET, recursive=True)
            for obj in objects:
                if not obj.object_name.endswith('.pdf'): continue
                
                meta = extract_metadata(obj.object_name)
                
                # Aplicar filtros
                if data.get('año') and meta['año'] != data['año']: continue
                if data.get('banco') and meta['banco'] != data['banco']: continue
                if data.get('mes') and meta['mes'] != data['mes']: continue
                if data.get('razon_social') and meta['razon_social'] != data['razon_social']: continue
                
                # Buscar código en PDF
                if search_in_pdf(obj.object_name, codigo_empleado):
                    results.append({
                        'filename': obj.object_name,
                        'metadata': meta,
                        'download_url': f'/api/download/{obj.object_name}',
                        'size_kb': round(obj.size / 1024, 2)
                    })
                
                meta = extract_metadata(obj.object_name)
                
                # Aplicar filtros
                if data.get('año') and meta['año'] != data['año']: continue
                if data.get('banco') and meta['banco'] != data['banco']: continue
                if data.get('mes') and meta['mes'] != data['mes']: continue
                if data.get('razon_social') and meta['razon_social'] != data['razon_social']: continue
                
                # Buscar código en PDF
                if search_in_pdf(obj.object_name, codigo_empleado):
                    results.append({
                        'filename': obj.object_name,
                        'metadata': meta,
                        'download_url': f'/api/download/{obj.object_name}',
                        'size_kb': round(obj.size / 1024, 2)
                    })
                
        except Exception as e:
            return Response({'error': str(e), 'total': 0, 'results': []}, status=500)
        
        elapsed = round((time.time() - start_time) * 1000, 2)
        return Response({
            'total': len(results),
            'results': results,
            'search_time_ms': elapsed,
            'source': 'minio_direct'
        })

class DownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, filename):
        try:
            # MinIO response
            response = minio_client.get_object(settings.MINIO_BUCKET, filename)
            
            # Log audit
            DownloadLog.objects.create(
                user=request.user,
                filename=filename,
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
            # Streaming response
            response_headers = {
                'Content-Disposition': f'attachment; filename="{filename.split("/")[-1]}"'
            }
            return StreamingHttpResponse(
                response.stream(amt=8192),
                content_type='application/pdf',
                headers=response_headers
            )
        except Exception as e:
            return Response({'error': 'Archivo no encontrado'}, status=404)

class SyncIndexView(APIView):
    """
    Sincronización INTELIGENTE del índice con BATCH PROCESSING.
    POST /api/index/sync
    
    DETECTA ARCHIVOS MOVIDOS usando tamaño + hash MD5.
    """
    """
    Sincronización INTELIGENTE del índice con BATCH PROCESSING.
    POST /api/index/sync
    
    DETECTA ARCHIVOS MOVIDOS usando tamaño + hash MD5.
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        import logging
        logger = logging.getLogger(__name__)
        
        import logging
        logger = logging.getLogger(__name__)
        
        global _minio_list_cache
        data = request.data or {}
        data = request.data or {}
        batch_size = min(int(data.get('batch_size', 50)), 200)
        skip_new = data.get('skip_new', False)
        
        start_time = time.time()
        new_files = 0
        moved_files = 0
        moved_details = []
        removed_orphans = 0
        removed_orphans = 0
        errors = 0
        
        try:
            # ═══════════════════════════════════════════════════
            # PASO 1: Listar MinIO (con caché de 60s)
            # ═══════════════════════════════════════════════════
            now = time.time()
            if _minio_list_cache['data'] is None or (now - _minio_list_cache['time']) > 60:
                logger.info("Listing MinIO (cache expired or empty)...")
                minio_all = []
                for obj in minio_client.list_objects(settings.MINIO_BUCKET, recursive=True):
                    if obj.object_name.endswith('.pdf'):
                        minio_all.append(obj)
                _minio_list_cache = {'time': now, 'data': minio_all}
            
            objects_list = _minio_list_cache['data']
            minio_map = {obj.object_name: obj for obj in objects_list}
            minio_names = set(minio_map.keys())
            
            # Construir índice por hash para detección de movidos
            minio_by_hash = {}
            for obj in objects_list:
                md5_hash = obj.etag.strip('"') if obj.etag else None
                if md5_hash:
                    key = (obj.size, md5_hash)
                    if key not in minio_by_hash:
                        minio_by_hash[key] = []
                    minio_by_hash[key].append(obj)
            
            # CASO ESPECIAL: No hay PDFs
            indexed_count = PDFIndex.objects.count()
            if len(minio_names) == 0 and indexed_count == 0:
                elapsed = round(time.time() - start_time, 2)
                return Response({
                    'message': 'No hay PDFs en MinIO ni en el índice',
                    'total_in_minio': 0,
                    'total_indexed': 0,
                    'new_files': 0,
                    'moved_files': 0,
                    'removed_orphans': 0,
                    'pending_new': 0,
                    'has_more': False,
                    'progress_percent': 100,
                    'errors': 0,
                    'time_seconds': elapsed,
                    'batch_size': batch_size
                })
            
            # ═══════════════════════════════════════════════════
            # PASO 2: Obtener indexados y detectar huérfanos
            # ═══════════════════════════════════════════════════
            indexed_qs = PDFIndex.objects.all()
            indexed_map = {r.minio_object_name: r for r in indexed_qs}
            indexed_names = set(indexed_map.keys())
            
            orphan_names = indexed_names - minio_names
            
            # Índice de huérfanos por tamaño + hash
            orphan_by_hash = {}
            for name in orphan_names:
                record = indexed_map[name]
                if record.md5_hash and record.size_bytes:
                    key = (record.size_bytes, record.md5_hash)
                    if key not in orphan_by_hash:
                        orphan_by_hash[key] = []
                    orphan_by_hash[key].append(record)
            
            # ═══════════════════════════════════════════════════
            # PASO 3: Detectar archivos movidos
            # ═══════════════════════════════════════════════════
            new_names = minio_names - indexed_names
            truly_new_names = []
            
            for name in new_names:
                obj = minio_map[name]
                md5 = obj.etag.strip('"') if obj.etag else None
                key = (obj.size, md5) if md5 else None
                
                if key and key in orphan_by_hash and orphan_by_hash[key]:
                    # ¡Archivo MOVIDO detectado!
                    orphan_rec = orphan_by_hash[key].pop(0)
                    old_path = orphan_rec.minio_object_name
                    
                    try:
                        meta = extract_metadata(name)
                        orphan_rec.minio_object_name = name
                        orphan_rec.razon_social = meta['razon_social']
                        orphan_rec.banco = meta['banco']
                        orphan_rec.año = meta['año']
                        orphan_rec.mes = meta['mes']
                        orphan_rec.tipo_documento = meta['tipo_documento']
                        orphan_rec.last_modified = obj.last_modified
                        orphan_rec.indexed_at = datetime.utcnow()
                        orphan_rec.save()
                        
                        moved_files += 1
                        if len(moved_details) < 20:
                            moved_details.append({
                                'old_path': old_path,
                                'new_path': name
                            })
                        
                        # Quitar de huérfanos (vieja ruta)
                        orphan_names.discard(old_path)
                        
                    except Exception as e:
                        logger.error(f"✗ Error procesando archivo movido {name}: {e}")
                        errors += 1
                else:
                    truly_new_names.append(name)
            
            # ═══════════════════════════════════════════════════
            # PASO 4: Eliminar huérfanos restantes
            # ═══════════════════════════════════════════════════
            if orphan_names:
                PDFIndex.objects.filter(minio_object_name__in=orphan_names).delete()
                removed_orphans = len(orphan_names)
            
            # ═══════════════════════════════════════════════════
            # PASO 5: Indexar nuevos en batch
            # ═══════════════════════════════════════════════════
            total_truly_new = len(truly_new_names)
            pending_new = total_truly_new
            
            if not skip_new and truly_new_names:
                batch = truly_new_names[:batch_size]
                for name in batch:
                    try:
                        obj = minio_map[name]
                        meta = extract_metadata(name)
                        text, codigos = extract_text_from_pdf(name)
                        
                        PDFIndex.objects.create(
                            minio_object_name=name,
                            razon_social=meta['razon_social'],
                            banco=meta['banco'],
                            mes=meta['mes'],
                            año=meta['año'],
                            tipo_documento=meta['tipo_documento'],
                            size_bytes=obj.size,
                            md5_hash=obj.etag.strip('"') if obj.etag else None,
                            codigos_empleado=','.join(codigos) if codigos else '',
                            last_modified=obj.last_modified,
                            is_indexed=bool(text)
                        )
                        new_files += 1
                        pending_new -= 1
                    except Exception as e:
                        logger.error(f"✗ Error indexando {name}: {e}")
                        errors += 1
                        pending_new -= 1
            
            elapsed = round(time.time() - start_time, 2)
            has_more = pending_new > 0 and not skip_new
            
            # Calcular progreso
            if total_truly_new > 0:
                progress_percent = round(((total_truly_new - pending_new) / total_truly_new) * 100)
            else:
                progress_percent = 100
            
            result = {
                'message': 'Sincronización completada' if not has_more else f'Lote procesado ({new_files} de {total_truly_new})',
                'total_in_minio': len(minio_names),
                'total_indexed': PDFIndex.objects.count(),
                'new_files': new_files,
                'moved_files': moved_files,
                'removed_orphans': removed_orphans,
                'pending_new': pending_new,
                'has_more': has_more,
                'progress_percent': progress_percent,
                'errors': errors,
                'time_seconds': elapsed,
                'batch_size': batch_size
            }
            
            if moved_details:
                result['moved_details'] = moved_details
            
            status_log = "parcial" if has_more else "completa"
            logger.info(f"✓ Sincronización {status_log}: {new_files} nuevos, {moved_files} movidos, {removed_orphans} eliminados, {pending_new} pendientes en {elapsed}s")
            
            return Response(result)
            
        except Exception as e:
            logger.error(f"Error en sincronización: {e}")
            return Response({'error': f'Error inesperado: {str(e)}'}, status=500)
            
            objects_list = _minio_list_cache['data']
            minio_map = {obj.object_name: obj for obj in objects_list}
            minio_names = set(minio_map.keys())
            
            # Construir índice por hash para detección de movidos
            minio_by_hash = {}
            for obj in objects_list:
                md5_hash = obj.etag.strip('"') if obj.etag else None
                if md5_hash:
                    key = (obj.size, md5_hash)
                    if key not in minio_by_hash:
                        minio_by_hash[key] = []
                    minio_by_hash[key].append(obj)
            
            # CASO ESPECIAL: No hay PDFs
            indexed_count = PDFIndex.objects.count()
            if len(minio_names) == 0 and indexed_count == 0:
                elapsed = round(time.time() - start_time, 2)
                return Response({
                    'message': 'No hay PDFs en MinIO ni en el índice',
                    'total_in_minio': 0,
                    'total_indexed': 0,
                    'new_files': 0,
                    'moved_files': 0,
                    'removed_orphans': 0,
                    'pending_new': 0,
                    'has_more': False,
                    'progress_percent': 100,
                    'errors': 0,
                    'time_seconds': elapsed,
                    'batch_size': batch_size
                })
            
            # ═══════════════════════════════════════════════════
            # PASO 2: Obtener indexados y detectar huérfanos
            # ═══════════════════════════════════════════════════
            indexed_qs = PDFIndex.objects.all()
            indexed_map = {r.minio_object_name: r for r in indexed_qs}
            indexed_names = set(indexed_map.keys())
            
            orphan_names = indexed_names - minio_names
            
            # Índice de huérfanos por tamaño + hash
            orphan_by_hash = {}
            for name in orphan_names:
                record = indexed_map[name]
                if record.md5_hash and record.size_bytes:
                    key = (record.size_bytes, record.md5_hash)
                    if key not in orphan_by_hash:
                        orphan_by_hash[key] = []
                    orphan_by_hash[key].append(record)
            
            # ═══════════════════════════════════════════════════
            # PASO 3: Detectar archivos movidos
            # ═══════════════════════════════════════════════════
            new_names = minio_names - indexed_names
            truly_new_names = []
            
            for name in new_names:
                obj = minio_map[name]
                md5 = obj.etag.strip('"') if obj.etag else None
                key = (obj.size, md5) if md5 else None
                
                if key and key in orphan_by_hash and orphan_by_hash[key]:
                    # ¡Archivo MOVIDO detectado!
                    orphan_rec = orphan_by_hash[key].pop(0)
                    old_path = orphan_rec.minio_object_name
                    
                    try:
                        meta = extract_metadata(name)
                        orphan_rec.minio_object_name = name
                        orphan_rec.razon_social = meta['razon_social']
                        orphan_rec.banco = meta['banco']
                        orphan_rec.año = meta['año']
                        orphan_rec.mes = meta['mes']
                        orphan_rec.tipo_documento = meta['tipo_documento']
                        orphan_rec.last_modified = obj.last_modified
                        orphan_rec.indexed_at = datetime.utcnow()
                        orphan_rec.save()
                        
                        moved_files += 1
                        if len(moved_details) < 20:
                            moved_details.append({
                                'old_path': old_path,
                                'new_path': name
                            })
                        
                        # Quitar de huérfanos (vieja ruta)
                        orphan_names.discard(old_path)
                        
                    except Exception as e:
                        logger.error(f"✗ Error procesando archivo movido {name}: {e}")
                        errors += 1
                else:
                    truly_new_names.append(name)
            
            # ═══════════════════════════════════════════════════
            # PASO 4: Eliminar huérfanos restantes
            # ═══════════════════════════════════════════════════
            if orphan_names:
                PDFIndex.objects.filter(minio_object_name__in=orphan_names).delete()
                removed_orphans = len(orphan_names)
            
            # ═══════════════════════════════════════════════════
            # PASO 5: Indexar nuevos en batch
            # ═══════════════════════════════════════════════════
            total_truly_new = len(truly_new_names)
            pending_new = total_truly_new
            
            if not skip_new and truly_new_names:
                batch = truly_new_names[:batch_size]
                for name in batch:
                    try:
                        obj = minio_map[name]
                        meta = extract_metadata(name)
                        text, codigos = extract_text_from_pdf(name)
                        
                        PDFIndex.objects.create(
                            minio_object_name=name,
                            razon_social=meta['razon_social'],
                            banco=meta['banco'],
                            mes=meta['mes'],
                            año=meta['año'],
                            tipo_documento=meta['tipo_documento'],
                            size_bytes=obj.size,
                            md5_hash=obj.etag.strip('"') if obj.etag else None,
                            codigos_empleado=','.join(codigos) if codigos else '',
                            last_modified=obj.last_modified,
                            is_indexed=bool(text)
                        )
                        new_files += 1
                        pending_new -= 1
                    except Exception as e:
                        logger.error(f"✗ Error indexando {name}: {e}")
                        errors += 1
                        pending_new -= 1
            
            elapsed = round(time.time() - start_time, 2)
            has_more = pending_new > 0 and not skip_new
            
            # Calcular progreso
            if total_truly_new > 0:
                progress_percent = round(((total_truly_new - pending_new) / total_truly_new) * 100)
            else:
                progress_percent = 100
            
            result = {
                'message': 'Sincronización completada' if not has_more else f'Lote procesado ({new_files} de {total_truly_new})',
                'total_in_minio': len(minio_names),
                'total_indexed': PDFIndex.objects.count(),
                'new_files': new_files,
                'moved_files': moved_files,
                'removed_orphans': removed_orphans,
                'pending_new': pending_new,
                'has_more': has_more,
                'progress_percent': progress_percent,
                'errors': errors,
                'time_seconds': elapsed,
                'batch_size': batch_size
            }
            
            if moved_details:
                result['moved_details'] = moved_details
            
            status_log = "parcial" if has_more else "completa"
            logger.info(f"✓ Sincronización {status_log}: {new_files} nuevos, {moved_files} movidos, {removed_orphans} eliminados, {pending_new} pendientes en {elapsed}s")
            
            return Response(result)
            
        except Exception as e:
            logger.error(f"Error en sincronización: {e}")
            return Response({'error': f'Error inesperado: {str(e)}'}, status=500)

class PopulateHashesView(APIView):
    """
    Poblar SOLO los hashes MD5 de registros existentes.
    POST /api/index/populate-hashes
    
    Este endpoint es RÁPIDO porque:
    - NO descarga PDFs
    - NO extrae texto
    - Solo lee el ETag de MinIO (ya contiene el MD5)
    """
    """
    Poblar SOLO los hashes MD5 de registros existentes.
    POST /api/index/populate-hashes
    
    Este endpoint es RÁPIDO porque:
    - NO descarga PDFs
    - NO extrae texto
    - Solo lee el ETag de MinIO (ya contiene el MD5)
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        import logging
        logger = logging.getLogger(__name__)
        
        data = request.data or {}
        batch_size = min(int(data.get('batch_size', 500)), 2000)
        import logging
        logger = logging.getLogger(__name__)
        
        data = request.data or {}
        batch_size = min(int(data.get('batch_size', 500)), 2000)
        
        start_time = time.time()
        updated = 0
        not_found = 0
        errors = 0
        
        try:
            # ═══════════════════════════════════════════════════
            # PASO 1: Obtener mapa de MinIO con ETags
            # ═══════════════════════════════════════════════════
            minio_etags = {}
            for obj in minio_client.list_objects(settings.MINIO_BUCKET, recursive=True):
                if obj.object_name.endswith('.pdf') and obj.etag:
                    minio_etags[obj.object_name] = {
                        'hash': obj.etag.strip('"'),
                        'size': obj.size
                    }
            
            # ═══════════════════════════════════════════════════
            # PASO 2: Buscar registros SIN hash
            # ═══════════════════════════════════════════════════
            total_without_hash = PDFIndex.objects.filter(
                Q(md5_hash__isnull=True) | Q(md5_hash='')
            ).count()
            
            # CASO ESPECIAL: No hay registros pendientes
            if total_without_hash == 0:
                total_records = PDFIndex.objects.count()
                elapsed = round(time.time() - start_time, 2)
                return Response({
                    'message': 'No hay registros pendientes de hash' if total_records > 0 else 'No hay PDFs indexados',
                    'updated': 0,
                    'not_found_in_minio': 0,
                    'pending': 0,
                    'has_more': False,
                    'progress_percent': 100,
                    'errors': 0,
                    'time_seconds': elapsed,
                    'batch_size': batch_size,
                    'total_records': total_records
                })
            
            qs = PDFIndex.objects.filter(
                Q(md5_hash__isnull=True) | Q(md5_hash='')
            ).exclude(minio_object_name='')[:batch_size]
            
            # ═══════════════════════════════════════════════════
            # PASO 3: Actualizar hashes
            # ═══════════════════════════════════════════════════
            for record in qs:
                if record.minio_object_name in minio_etags:
                    try:
                        info = minio_etags[record.minio_object_name]
                        record.md5_hash = info['hash']
                        record.size_bytes = info['size']
                        record.save()
                        updated += 1
                    except Exception as e:
                        logger.error(f"Error actualizando hash de {record.minio_object_name}: {e}")
                        errors += 1
                else:
                    not_found += 1
            
            elapsed = round(time.time() - start_time, 2)
            pending = total_without_hash - updated
            has_more = pending > 0
            
            # Calcular progreso
            total_records = PDFIndex.objects.count()
            if total_records > 0:
                progress_percent = round(((total_records - pending) / total_records) * 100, 1)
            else:
                progress_percent = 100
            
            result = {
                'message': 'Hashes poblados' if not has_more else f'Lote procesado ({updated} de {total_without_hash})',
                'updated': updated,
                'not_found_in_minio': not_found,
                'pending': pending,
                'has_more': has_more,
                'progress_percent': progress_percent,
                'errors': errors,
                'time_seconds': elapsed,
                'batch_size': batch_size
            }
            
            logger.info(f"✓ Populate hashes: {updated} actualizados, {pending} pendientes en {elapsed}s")
            
            return Response(result)
            
        except Exception as e:
            logger.error(f"Error en populate hashes: {e}")
            return Response({'error': f'Error inesperado: {str(e)}'}, status=500)
        start_time = time.time()
        updated = 0
        not_found = 0
        errors = 0
        
        try:
            # ═══════════════════════════════════════════════════
            # PASO 1: Obtener mapa de MinIO con ETags
            # ═══════════════════════════════════════════════════
            minio_etags = {}
            for obj in minio_client.list_objects(settings.MINIO_BUCKET, recursive=True):
                if obj.object_name.endswith('.pdf') and obj.etag:
                    minio_etags[obj.object_name] = {
                        'hash': obj.etag.strip('"'),
                        'size': obj.size
                    }
            
            # ═══════════════════════════════════════════════════
            # PASO 2: Buscar registros SIN hash
            # ═══════════════════════════════════════════════════
            total_without_hash = PDFIndex.objects.filter(
                Q(md5_hash__isnull=True) | Q(md5_hash='')
            ).count()
            
            # CASO ESPECIAL: No hay registros pendientes
            if total_without_hash == 0:
                total_records = PDFIndex.objects.count()
                elapsed = round(time.time() - start_time, 2)
                return Response({
                    'message': 'No hay registros pendientes de hash' if total_records > 0 else 'No hay PDFs indexados',
                    'updated': 0,
                    'not_found_in_minio': 0,
                    'pending': 0,
                    'has_more': False,
                    'progress_percent': 100,
                    'errors': 0,
                    'time_seconds': elapsed,
                    'batch_size': batch_size,
                    'total_records': total_records
                })
            
            qs = PDFIndex.objects.filter(
                Q(md5_hash__isnull=True) | Q(md5_hash='')
            ).exclude(minio_object_name='')[:batch_size]
            
            # ═══════════════════════════════════════════════════
            # PASO 3: Actualizar hashes
            # ═══════════════════════════════════════════════════
            for record in qs:
                if record.minio_object_name in minio_etags:
                    try:
                        info = minio_etags[record.minio_object_name]
                        record.md5_hash = info['hash']
                        record.size_bytes = info['size']
                        record.save()
                        updated += 1
                    except Exception as e:
                        logger.error(f"Error actualizando hash de {record.minio_object_name}: {e}")
                        errors += 1
                else:
                    not_found += 1
            
            elapsed = round(time.time() - start_time, 2)
            pending = total_without_hash - updated
            has_more = pending > 0
            
            # Calcular progreso
            total_records = PDFIndex.objects.count()
            if total_records > 0:
                progress_percent = round(((total_records - pending) / total_records) * 100, 1)
            else:
                progress_percent = 100
            
            result = {
                'message': 'Hashes poblados' if not has_more else f'Lote procesado ({updated} de {total_without_hash})',
                'updated': updated,
                'not_found_in_minio': not_found,
                'pending': pending,
                'has_more': has_more,
                'progress_percent': progress_percent,
                'errors': errors,
                'time_seconds': elapsed,
                'batch_size': batch_size
            }
            
            logger.info(f"✓ Populate hashes: {updated} actualizados, {pending} pendientes en {elapsed}s")
            
            return Response(result)
            
        except Exception as e:
            logger.error(f"Error en populate hashes: {e}")
            return Response({'error': f'Error inesperado: {str(e)}'}, status=500)

class IndexStatsView(APIView):
    """
    Estadísticas del índice de PDFs.
    GET /api/index/stats
    """
    """
    Estadísticas del índice de PDFs.
    GET /api/index/stats
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        total = PDFIndex.objects.count()
        total_size = PDFIndex.objects.aggregate(Sum('size_bytes'))['size_bytes__sum'] or 0
        
        # Último indexado
        last = PDFIndex.objects.order_by('-indexed_at').first() if total > 0 else None
        
        total = PDFIndex.objects.count()
        total_size = PDFIndex.objects.aggregate(Sum('size_bytes'))['size_bytes__sum'] or 0
        
        # Último indexado
        last = PDFIndex.objects.order_by('-indexed_at').first() if total > 0 else None
        
        return Response({
            'total_indexed': total,
            'total_size_gb': round(total_size / (1024**3), 2),
            'total_indexed': total,
            'total_size_gb': round(total_size / (1024**3), 2),
            'by_year': {x['año']: x['c'] for x in PDFIndex.objects.values('año').annotate(c=Count('id'))},
            'by_razon_social': {x['razon_social']: x['c'] for x in PDFIndex.objects.values('razon_social').annotate(c=Count('id'))},
            'by_banco': {x['banco']: x['c'] for x in PDFIndex.objects.values('banco').annotate(c=Count('id'))},
            'last_indexed': last.indexed_at.isoformat() if last and last.indexed_at else None,
            'indexed_successfully': PDFIndex.objects.filter(is_indexed=True).count(),
            'with_errors': PDFIndex.objects.filter(is_indexed=False).count(),
            'by_razon_social': {x['razon_social']: x['c'] for x in PDFIndex.objects.values('razon_social').annotate(c=Count('id'))},
            'by_banco': {x['banco']: x['c'] for x in PDFIndex.objects.values('banco').annotate(c=Count('id'))},
            'last_indexed': last.indexed_at.isoformat() if last and last.indexed_at else None,
            'indexed_successfully': PDFIndex.objects.filter(is_indexed=True).count(),
            'with_errors': PDFIndex.objects.filter(is_indexed=False).count()
        })

class ReindexView(APIView):
    """
    Reindexar todos los PDFs de MinIO en PostgreSQL.
    POST /api/reindex
    
    INCLUYE: Eliminación de índices huérfanos (PDFs eliminados de MinIO)
    """
    """
    Reindexar todos los PDFs de MinIO en PostgreSQL.
    POST /api/reindex
    
    INCLUYE: Eliminación de índices huérfanos (PDFs eliminados de MinIO)
    """
    permission_classes = [IsAdminUser]
    
    def post(self, request):
        import logging
        logger = logging.getLogger(__name__)
        
        data = request.data or {}
        clean_orphans = data.get('clean_orphans', True)
        
        start_time = time.time()
        indexed_count = 0
        new_count = 0
        updated_count = 0
        error_count = 0
        orphans_removed = 0
        
        try:
            # Paso 1: Obtener lista de PDFs en MinIO
            minio_objects = {}
            for obj in minio_client.list_objects(settings.MINIO_BUCKET, recursive=True):
                if obj.object_name.endswith('.pdf'):
                    minio_objects[obj.object_name] = obj
            
            logger.info(f"📁 Encontrados {len(minio_objects)} PDFs en MinIO")
            
            # Paso 2: Eliminar índices huérfanos
            if clean_orphans:
                indexed_names = set(PDFIndex.objects.values_list('minio_object_name', flat=True))
                orphan_names = indexed_names - set(minio_objects.keys())
                
                if orphan_names:
                    PDFIndex.objects.filter(minio_object_name__in=orphan_names).delete()
                    orphans_removed = len(orphan_names)
                    logger.info(f"🗑️ Eliminados {orphans_removed} índices huérfanos")
            
            # Paso 3: Indexar PDFs nuevos o actualizados
            to_process = []
            for object_name, obj in minio_objects.items():
                try:
                    existing = PDFIndex.objects.filter(minio_object_name=object_name).first()
                    if not existing:
                        to_process.append((obj, 'new'))
                        new_count += 1
                    elif existing.last_modified != obj.last_modified:
                        to_process.append((obj, 'update'))
                        updated_count += 1
                    else:
                        indexed_count += 1
                except Exception as e:
                    error_count += 1
            
            # Paso 4: Procesar nuevos/actualizados (secuencial para Django ORM)
            for obj, action in to_process:
                try:
                    meta = extract_metadata(obj.object_name)
                    text, codigos = extract_text_from_pdf(obj.object_name)
                    md5_hash = obj.etag.strip('"') if obj.etag else None
                    
                    PDFIndex.objects.update_or_create(
                        minio_object_name=obj.object_name,
                        defaults={
                            'razon_social': meta['razon_social'],
                            'banco': meta['banco'],
                            'mes': meta['mes'],
                            'año': meta['año'],
                            'tipo_documento': meta['tipo_documento'],
                            'size_bytes': obj.size,
                            'md5_hash': md5_hash,
                            'codigos_empleado': ','.join(codigos) if codigos else '',
                            'last_modified': obj.last_modified,
                            'is_indexed': bool(text),
                            'index_error': None if text else 'Error extrayendo texto'
                        }
                    )
                    indexed_count += 1
                except Exception as e:
                    error_count += 1
                    logger.error(f"✗ Error indexando {obj.object_name}: {e}")
            
            elapsed = round(time.time() - start_time, 2)
            logger.info(f"✓ Indexación completada: {indexed_count} PDFs en {elapsed}s")
            
            return Response({
                'message': 'Indexación completada',
                'total_in_minio': len(minio_objects),
                'total_indexed': indexed_count,
                'new_indexed': new_count,
                'updated': updated_count,
                'orphans_removed': orphans_removed,
                'errors': error_count,
                'time_seconds': elapsed
            })
            
        except Exception as e:
            logger.error(f"Error en reindexación: {e}")
            return Response({'error': f'Error inesperado: {str(e)}'}, status=500)


# ═══════════════════════════════════════════════════
# FILE MANAGEMENT VIEWS (Migrated from Flask)
# ═══════════════════════════════════════════════════

class FilesListView(APIView):
    """
    Listar PDFs indexados desde PostgreSQL con paginación y filtros.
    GET /api/files/list
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Parámetros de filtrado
        folder_filter = request.query_params.get('folder', '').strip()
        search_query = request.query_params.get('search', '').strip()
        año = request.query_params.get('año', '').strip()
        mes = request.query_params.get('mes', '').strip()
        banco = request.query_params.get('banco', '').strip()
        razon_social = request.query_params.get('razon_social', '').strip()
        tipo_documento = request.query_params.get('tipo_documento', '').strip()

        # Parámetros de paginación y ordenamiento
        page = int(request.query_params.get('page', 1))
        per_page = min(int(request.query_params.get('per_page', 100)), 500)
        sort_field = request.query_params.get('sort', 'indexed_at')
        order = request.query_params.get('order', 'desc')

        try:
            query = Q(is_indexed=True)

            if folder_filter:
                query &= Q(minio_object_name__startswith=folder_filter)
            if search_query:
                query &= Q(minio_object_name__icontains=search_query)
            if año:
                query &= Q(año=año)
            if mes:
                query &= Q(mes=mes)
            if banco:
                query &= Q(banco=banco)
            if razon_social:
                query &= Q(razon_social=razon_social)
            if tipo_documento:
                query &= Q(tipo_documento__icontains=tipo_documento)

            # Ordenamiento
            order_prefix = '' if order == 'asc' else '-'
            field_map = {
                'indexed_at': 'indexed_at',
                'last_modified': 'last_modified',
                'size': 'size_bytes',
                'filename': 'minio_object_name'
            }
            order_field = field_map.get(sort_field, 'indexed_at')
            ordering = f'{order_prefix}{order_field}'

            queryset = PDFIndex.objects.filter(query).order_by(ordering)
            total = queryset.count()

            # Paginación manual
            start = (page - 1) * per_page
            end = start + per_page
            paginated = queryset[start:end]

            total_pages = (total + per_page - 1) // per_page

            files = []
            for record in paginated:
                size_bytes = record.size_bytes or 0
                if size_bytes < 1024:
                    size_human = f"{size_bytes} B"
                elif size_bytes < 1024 * 1024:
                    size_human = f"{size_bytes / 1024:.1f} KB"
                else:
                    size_human = f"{size_bytes / (1024 * 1024):.1f} MB"

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

            return Response({
                'files': files,
                'total': total,
                'page': page,
                'per_page': per_page,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1
            })

        except Exception as e:
            return Response({'error': f'Error al listar archivos: {str(e)}'}, status=500)


class FilesUploadView(APIView):
    """
    Subir uno o varios PDFs a MinIO y auto-indexarlos.
    POST /api/files/upload (multipart/form-data)
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        from io import BytesIO
        import logging
        logger = logging.getLogger(__name__)

        files = request.FILES.getlist('files[]')
        folder = request.POST.get('folder', '').strip()

        if not files:
            return Response({'error': 'No se proporcionaron archivos.'}, status=400)

        uploaded = []
        errors = []

        for file in files:
            if not file or file.name == '':
                continue

            if not file.name.lower().endswith('.pdf'):
                errors.append({'filename': file.name, 'error': 'Solo se permiten archivos PDF'})
                continue

            try:
                if folder and not folder.endswith('/'):
                    folder += '/'

                object_name = f"{folder}{file.name}" if folder else file.name

                # Leer contenido del archivo
                file_content = file.read()
                file_size = len(file_content)

                # Subir a MinIO
                minio_client.put_object(
                    settings.MINIO_BUCKET,
                    object_name,
                    BytesIO(file_content),
                    length=file_size,
                    content_type='application/pdf'
                )

                logger.info(f"✓ Archivo subido: {object_name}")

                # Auto-indexar
                indexed = False
                try:
                    meta = extract_metadata(object_name)
                    # Extraer texto y códigos
                    text, codigos = extract_text_from_pdf(object_name)

                    PDFIndex.objects.update_or_create(
                        minio_object_name=object_name,
                        defaults={
                            'razon_social': meta['razon_social'],
                            'banco': meta['banco'],
                            'mes': meta['mes'],
                            'año': meta['año'],
                            'tipo_documento': meta['tipo_documento'],
                            'size_bytes': file_size,
                            'codigos_empleado': ','.join(codigos) if codigos else '',
                            'is_indexed': bool(text)
                        }
                    )
                    indexed = True
                    logger.info(f"✓ Archivo indexado: {object_name}")
                except Exception as idx_error:
                    logger.error(f"✗ Error indexando {object_name}: {idx_error}")

                uploaded.append({
                    'filename': file.name,
                    'path': object_name,
                    'size': file_size,
                    'indexed': indexed
                })

            except Exception as e:
                logger.error(f"✗ Error subiendo {file.name}: {e}")
                errors.append({'filename': file.name, 'error': str(e)})

        return Response({
            'success': len(uploaded) > 0,
            'uploaded': uploaded,
            'errors': errors,
            'total_uploaded': len(uploaded),
            'total_indexed': sum(1 for u in uploaded if u['indexed']),
            'total_errors': len(errors)
        }, status=201 if uploaded else 400)


class CreateFolderView(APIView):
    """
    Crea una 'carpeta' en MinIO creando un objeto placeholder.
    POST /api/files/create-folder
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        from io import BytesIO
        from minio.error import S3Error
        import logging
        logger = logging.getLogger(__name__)

        path = request.data.get('path', '').strip()
        if not path:
            return Response({'error': 'Debe proporcionar la ruta de la carpeta.'}, status=400)

        if not path.endswith('/'):
            path = path + '/'

        # Sanitizar caracteres inválidos
        safe_path = re.sub(r'[<>:"\\|?*]', '', path)

        placeholder_name = safe_path + '.placeholder'
        try:
            minio_client.put_object(
                settings.MINIO_BUCKET,
                placeholder_name,
                BytesIO(b''),
                length=0,
                content_type='application/octet-stream'
            )
            logger.info(f"✓ Carpeta creada en MinIO (placeholder): {placeholder_name}")
            return Response({'success': True, 'path': safe_path}, status=201)
        except S3Error as e:
            logger.error(f"✗ Error creando carpeta {safe_path}: {e}")
            return Response({'error': f'Error en MinIO: {str(e)}'}, status=500)
        except Exception as e:
            logger.error(f"✗ Error creando carpeta {safe_path}: {e}")
            return Response({'error': f'Error: {str(e)}'}, status=500)


class FilesDeleteView(APIView):
    """
    Eliminar un archivo de MinIO y su índice en PostgreSQL.
    DELETE /api/files/delete
    """
    permission_classes = [IsAdminUser]

    def delete(self, request):
        from minio.error import S3Error
        import logging
        logger = logging.getLogger(__name__)

        file_path = request.data.get('path', '').strip()

        if not file_path:
            return Response({'error': 'Debe proporcionar la ruta del archivo.'}, status=400)

        try:
            # Eliminar de MinIO
            minio_client.remove_object(settings.MINIO_BUCKET, file_path)
            logger.info(f"✓ Archivo eliminado de MinIO: {file_path}")

            # Eliminar índice de PostgreSQL
            PDFIndex.objects.filter(minio_object_name=file_path).delete()
            logger.info(f"✓ Índice eliminado de PostgreSQL: {file_path}")

            return Response({
                'success': True,
                'message': 'Archivo eliminado correctamente',
                'path': file_path
            })

        except S3Error as e:
            if e.code == 'NoSuchKey':
                # El archivo no existe en MinIO, pero limpiar índice
                PDFIndex.objects.filter(minio_object_name=file_path).delete()
                return Response({'error': 'El archivo no existe en MinIO.'}, status=404)
            else:
                logger.error(f"✗ Error S3 eliminando {file_path}: {e}")
                return Response({'error': f'Error en MinIO: {str(e)}'}, status=500)
        except Exception as e:
            logger.error(f"✗ Error eliminando {file_path}: {e}")
            return Response({'error': f'Error al eliminar: {str(e)}'}, status=500)


class FoldersListView(APIView):
    """
    Lista carpetas disponibles usando el índice de PostgreSQL.
    GET /api/folders
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_time = time.time()
        parent = request.query_params.get('parent', '').strip()

        if parent and not parent.endswith('/'):
            parent += '/'

        try:
            # Obtener paths que empiezan con parent
            if parent:
                paths = PDFIndex.objects.filter(
                    minio_object_name__startswith=parent
                ).values_list('minio_object_name', flat=True)
            else:
                paths = PDFIndex.objects.values_list('minio_object_name', flat=True)

            # Extraer carpetas únicas del nivel actual
            folders = {}

            for path in paths:
                relative_path = path[len(parent):] if parent else path
                parts = relative_path.split('/')

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

            # Breadcrumb
            breadcrumb = []
            if parent:
                parts = parent.rstrip('/').split('/')
                accumulated = ''
                for part in parts:
                    accumulated += part + '/'
                    breadcrumb.append({'name': part, 'path': accumulated})

            elapsed = round((time.time() - start_time) * 1000, 2)

            parent_path = ''
            if parent and '/' in parent.rstrip('/'):
                parent_path = '/'.join(parent.rstrip('/').split('/')[:-1]) + '/'

            return Response({
                'folders': sorted(folders.values(), key=lambda x: x['name'].lower()),
                'current_path': parent,
                'breadcrumb': breadcrumb,
                'parent_path': parent_path,
                'time_ms': elapsed
            })

        except Exception as e:
            return Response({'error': f'Error al listar carpetas: {str(e)}'}, status=500)


class BulkSearchView(APIView):
    """
    Búsqueda masiva por múltiples códigos de empleado o DNI.
    POST /api/search/bulk
    
    JSON body: {
        "codigos": "12345678, 87654321, 11223344" o ["12345678", "87654321"],
        "año": "2025",
        "mes": "03",
        "banco": "BCP",
        "razon_social": "RESGUARDO",
        "tipo_documento": "CUADRO DE PERSONAL"
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        import logging
        logger = logging.getLogger(__name__)
        
        data = request.data
        codigos_input = data.get('codigos', [])
        
        # Limpiar y validar códigos
        if isinstance(codigos_input, str):
            codigos = [c.strip() for c in re.split(r'[,\s\n]+', codigos_input) if c.strip()]
        else:
            codigos = [str(c).strip() for c in codigos_input if str(c).strip()]
        
        # Eliminar duplicados manteniendo orden
        codigos = list(dict.fromkeys(codigos))
        
        if not codigos:
            return Response({
                'error': 'Debe proporcionar al menos un código de empleado o DNI.',
                'total': 0,
                'results': []
            }, status=400)
        
        if len(codigos) > 500:
            return Response({
                'error': 'Máximo 500 códigos por búsqueda.',
                'total': 0,
                'results': []
            }, status=400)
        
        # Filtros adicionales
        año = data.get('año', '').strip() if data.get('año') else ''
        mes = data.get('mes', '').strip() if data.get('mes') else ''
        banco = data.get('banco', '').strip() if data.get('banco') else ''
        razon_social = data.get('razon_social', '').strip() if data.get('razon_social') else ''
        tipo_documento = data.get('tipo_documento', '').strip() if data.get('tipo_documento') else ''
        
        try:
            # Construir query base con filtros
            query = Q(is_indexed=True)
            
            # Aplicar filtros adicionales
            if año:
                query &= Q(año=año)
            if mes:
                query &= Q(mes=mes)
            if banco:
                query &= Q(banco=banco)
            if razon_social:
                query &= Q(razon_social=razon_social)
            if tipo_documento:
                query &= Q(tipo_documento__icontains=tipo_documento)
            
            # Construir condiciones OR para todos los códigos
            codigo_conditions = Q()
            for codigo in codigos:
                codigo_conditions |= Q(codigos_empleado__icontains=codigo)
            
            query &= codigo_conditions
            
            # Ejecutar consulta
            all_records = PDFIndex.objects.filter(query)
            
            logger.info(f"Búsqueda masiva: {len(codigos)} códigos → {all_records.count()} registros")
            
            # Procesar resultados
            results = []
            codigos_encontrados = set()
            
            for record in all_records:
                codigos_en_pdf = record.codigos_empleado or ''
                codigos_match = []
                
                for codigo in codigos:
                    if codigo.lower() in codigos_en_pdf.lower():
                        codigos_match.append(codigo)
                        codigos_encontrados.add(codigo)
                
                if codigos_match:
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
            
            # Ordenar resultados
            results.sort(key=lambda x: (
                x['metadata'].get('año', ''), 
                x['metadata'].get('mes', ''), 
                x['filename']
            ))
            
            return Response({
                'total': len(results),
                'codigos_buscados': codigos,
                'codigos_encontrados': list(codigos_encontrados),
                'codigos_no_encontrados': codigos_no_encontrados,
                'results': results,
                'can_merge': len(results) > 1
            })
            
        except Exception as e:
            logger.error(f"Error en búsqueda masiva: {e}")
            return Response({
                'error': f'Error en la búsqueda: {str(e)}',
                'total': 0,
                'results': []
            }, status=500)


class MergePdfsView(APIView):
    """
    Combina múltiples PDFs en un único archivo para descargar.
    POST /api/merge-pdfs
    
    JSON body: {
        "paths": ["Planillas 2025/archivo1.pdf", "Planillas 2025/archivo2.pdf"],
        "output_name": "documentos_combinados" (opcional)
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from io import BytesIO
        from minio.error import S3Error
        import fitz  # PyMuPDF
        import logging
        logger = logging.getLogger(__name__)
        
        data = request.data
        paths = data.get('paths', [])
        output_name = data.get('output_name', 'documentos_combinados').strip()
        
        if not paths or len(paths) < 1:
            return Response({'error': 'Debe proporcionar al menos un archivo PDF.'}, status=400)
        
        if len(paths) > 100:
            return Response({'error': 'Máximo 100 archivos por fusión.'}, status=400)
        
        try:
            # Crear documento PDF combinado
            merged_pdf = fitz.open()
            files_merged = []
            errors = []
            
            for path in paths:
                try:
                    # Descargar PDF de MinIO
                    response = minio_client.get_object(settings.MINIO_BUCKET, path)
                    pdf_bytes = response.read()
                    response.close()
                    response.release_conn()
                    
                    # Abrir y añadir al documento combinado
                    src_pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
                    merged_pdf.insert_pdf(src_pdf)
                    src_pdf.close()
                    
                    files_merged.append(path)
                    logger.info(f"✓ Añadido al merge: {path}")
                    
                except S3Error as e:
                    logger.error(f"✗ Error descargando {path}: {e}")
                    errors.append({'path': path, 'error': str(e)})
                except Exception as e:
                    logger.error(f"✗ Error procesando {path}: {e}")
                    errors.append({'path': path, 'error': str(e)})
            
            if not files_merged:
                return Response({
                    'error': 'No se pudo procesar ningún archivo.',
                    'errors': errors
                }, status=400)
            
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
            try:
                DownloadLog.objects.create(
                    user=request.user,
                    filename=f"MERGED:{len(files_merged)}_archivos_{safe_name}.pdf",
                    ip_address=request.META.get('REMOTE_ADDR', '')
                )
            except Exception as log_error:
                logger.warning(f"No se pudo registrar descarga: {log_error}")
            
            logger.info(f"✓ PDF combinado: {len(files_merged)} archivos, {len(errors)} errores")
            
            from django.http import HttpResponse
            response = HttpResponse(
                output.read(),
                content_type='application/pdf'
            )
            response['Content-Disposition'] = f'attachment; filename="{safe_name}.pdf"'
            response['X-Files-Merged'] = str(len(files_merged))
            response['X-Merge-Errors'] = str(len(errors))
            
            return response
            
        except Exception as e:
            logger.error(f"✗ Error fusionando PDFs: {e}")
            return Response({'error': f'Error al fusionar PDFs: {str(e)}'}, status=500)