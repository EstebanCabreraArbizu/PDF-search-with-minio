from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.db.models import Q, Sum, Count
from django.http import StreamingHttpResponse
from auditlog.services import record_audit_event
from docrepo.models import Document, StorageObject
from docrepo.services import deactivate_document_by_storage_key, upsert_document_from_upload
from .models import PDFIndex, DownloadLog
from .serializers import PDFIndexSerializer
from .throttling import SearchRateThrottle, BulkSearchRateThrottle
from .utils import (
    minio_client, extract_metadata, search_in_pdf,
    extract_text_from_pdf, extract_text_from_pdf_bytes,
    infer_upload_metadata, build_auto_storage_prefix,
    BANCOS_VALIDOS, RAZONES_SOCIALES_VALIDAS
)
import hashlib
import time
from datetime import datetime
import re
from django.conf import settings
from django.shortcuts import render
from django.db import connection

# Cache simple en memoria para listado de MinIO (como en Flask app)
_minio_list_cache = {'time': 0, 'data': None}

CLASSIFICATION_DOMAIN_KEYWORDS = {
    'SEGUROS': ['SCTR', 'VIDA LEY', 'POLIZA', 'SEGURO', 'PENSION', 'SALUD'],
    'TREGISTRO': ['T-REGISTRO', 'TREGISTRO', 'ALTA', 'BAJA', 'PERSONAL EN FORMACION'],
    'CONSTANCIA_ABONO': ['FIN DE MES', 'CUADRE', 'PLANILLA', 'ABONOS ENVIADOS', 'TELECREDITO'],
}


def _build_upload_hints(request):
    return {
        'año': request.POST.get('año', request.POST.get('anio', '')),
        'mes': request.POST.get('mes', ''),
        'banco': request.POST.get('banco', ''),
        'razon_social': request.POST.get('razon_social', request.POST.get('empresa', '')),
        'tipo_documento': request.POST.get('tipo_documento', request.POST.get('tipo', '')),
    }


def _find_active_duplicate_by_hash_size(file_size, md5_hash):
    if file_size <= 0 or not md5_hash:
        return None

    return (
        StorageObject.objects.select_related('document')
        .filter(
            bucket_name=settings.MINIO_BUCKET,
            size_bytes=file_size,
            document__is_active=True,
        )
        .filter(Q(etag=md5_hash) | Q(document__source_hash_md5=md5_hash))
        .first()
    )


def _classification_missing_fields(meta, domain_code):
    missing = []

    if not str(meta.get('año', '')).strip():
        missing.append('año')
    if not str(meta.get('mes', '')).strip():
        missing.append('mes')
    razon_social = str(meta.get('razon_social', '')).strip().upper()
    if not razon_social or razon_social == 'DESCONOCIDO':
        missing.append('razon_social')
    if not str(meta.get('tipo_documento', '')).strip():
        missing.append('tipo_documento')

    if domain_code == 'CONSTANCIA_ABONO':
        banco = str(meta.get('banco', '')).strip().upper()
        if not banco or banco == 'GENERAL':
            missing.append('banco')

    if domain_code == 'TREGISTRO':
        tipo = str(meta.get('tipo_documento', '')).strip().upper()
        if tipo not in {'ALTA', 'BAJA', 'TREGISTRO'} and 'ALTA' not in tipo and 'BAJA' not in tipo:
            missing.append('tipo_movimiento')

    if domain_code == 'SEGUROS':
        tipo = str(meta.get('tipo_documento', '')).strip().upper()
        if not any(token in tipo for token in ['SCTR', 'VIDA LEY', 'SEGURO', 'POLIZA']):
            missing.append('tipo_seguro')

    return list(dict.fromkeys(missing))


def _classification_confidence(meta, hints, pdf_text, filename):
    score = 0.35
    domain_code = str(meta.get('domain_code') or 'CONSTANCIA_ABONO').strip().upper()

    if str(meta.get('año', '')).strip():
        score += 0.1
    if str(meta.get('mes', '')).strip():
        score += 0.1

    razon_social = str(meta.get('razon_social', '')).strip().upper()
    if razon_social and razon_social != 'DESCONOCIDO':
        score += 0.1

    hinted_fields = [
        hints.get('año'),
        hints.get('mes'),
        hints.get('banco'),
        hints.get('razon_social'),
        hints.get('tipo_documento'),
    ]
    hint_count = len([value for value in hinted_fields if str(value or '').strip()])
    score += min(hint_count * 0.05, 0.2)

    joined = f"{filename or ''} {pdf_text or ''}".upper()
    domain_keywords = CLASSIFICATION_DOMAIN_KEYWORDS.get(domain_code, [])
    matched_keywords = [token for token in domain_keywords if token in joined]
    if len(matched_keywords) >= 2:
        score += 0.2
    elif matched_keywords:
        score += 0.1

    if domain_code == 'CONSTANCIA_ABONO':
        banco = str(meta.get('banco', '')).strip().upper()
        if banco and banco != 'GENERAL':
            score += 0.08
        else:
            score -= 0.05

    score = max(0.05, min(0.99, score))
    return round(score, 2)


def _classification_warnings(meta, domain_code, confidence, duplicate, missing_fields):
    warnings = []

    if duplicate is not None:
        warnings.append('duplicado_hash_size')
    if confidence < float(getattr(settings, 'DOCREPO_CLASSIFICATION_MIN_CONFIDENCE', 0.7)):
        warnings.append('low_confidence')
    if missing_fields:
        warnings.append('metadata_incompleta')

    if domain_code == 'CONSTANCIA_ABONO' and str(meta.get('banco', '')).strip().upper() == 'GENERAL':
        warnings.append('banco_no_detectado')

    if domain_code == 'TREGISTRO':
        tipo = str(meta.get('tipo_documento', '')).strip().upper()
        if 'ALTA' not in tipo and 'BAJA' not in tipo:
            warnings.append('movimiento_no_determinado')

    if domain_code == 'SEGUROS':
        tipo = str(meta.get('tipo_documento', '')).strip().upper()
        if not any(token in tipo for token in ['SCTR', 'VIDA LEY', 'SEGURO', 'POLIZA']):
            warnings.append('tipo_seguro_no_determinado')

    return list(dict.fromkeys(warnings))


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


def seguros_ui(request):
    return render(
        request,
        'documents/search_seguros.html',
        {
            'active_module': 'seguros',
            'active_admin': '',
        },
    )


def tregistro_ui(request):
    return render(
        request,
        'documents/search_tregistro.html',
        {
            'active_module': 'tregistro',
            'active_admin': '',
        },
    )

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
                })
        except Exception as e:
            pass
            
        return Response({
            'años': [str(y) for y in range(datetime.now().year, 2018, -1)],
            'razones_sociales': RAZONES_SOCIALES_VALIDAS,
            'bancos': BANCOS_VALIDOS + ['GENERAL'],
            'meses': meses,
            'index_stats': {'total': 0, 'indexed': False, 'source': 'static_config'},
        })

class SearchView(APIView):
    """Búsqueda de PDFs con validaciones completas. POST /api/search"""
    permission_classes = [IsAuthenticated]
    throttle_classes = [SearchRateThrottle]

    def post(self, request):
        from datetime import datetime

        start_time = time.time()
        data = request.data
        codigo_empleado = str(data.get('codigo_empleado', '')).strip()
        use_index = data.get('use_index', True)

        if not codigo_empleado:
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
                pass

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
    permission_classes = [IsAdminUser]

    def post(self, request):
        import logging

        logger = logging.getLogger(__name__)

        global _minio_list_cache
        data = request.data or {}
        batch_size = min(int(data.get('batch_size', 50)), 200)
        skip_new = data.get('skip_new', False)
        dual_write_legacy = getattr(settings, 'DOCREPO_DUAL_WRITE_LEGACY_ENABLED', True)

        start_time = time.time()
        new_files = 0
        moved_files = 0
        moved_details = []
        removed_orphans = 0
        errors = 0

        try:
            now = time.time()
            if _minio_list_cache['data'] is None or (now - _minio_list_cache['time']) > 60:
                logger.info('Listing MinIO (cache expired or empty)...')
                minio_all = []
                for obj in minio_client.list_objects(settings.MINIO_BUCKET, recursive=True):
                    if obj.object_name.endswith('.pdf'):
                        minio_all.append(obj)
                _minio_list_cache = {'time': now, 'data': minio_all}

            objects_list = _minio_list_cache['data']
            minio_map = {obj.object_name: obj for obj in objects_list}
            minio_names = set(minio_map.keys())

            storage_rows = StorageObject.objects.select_related('document').filter(
                bucket_name=settings.MINIO_BUCKET,
                document__is_active=True,
            )
            storage_by_key = {row.object_key: row for row in storage_rows if row.object_key}
            indexed_names = set(storage_by_key.keys())

            indexed_count = Document.objects.filter(is_active=True, index_state__is_indexed=True).count()
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

            orphan_names = indexed_names - minio_names

            orphan_by_hash = {}
            for orphan_name in orphan_names:
                storage = storage_by_key.get(orphan_name)
                if storage is None:
                    continue

                md5_hash = (storage.etag or '').strip('"') or (storage.document.source_hash_md5 or '')
                if md5_hash and storage.size_bytes:
                    key = (storage.size_bytes, md5_hash)
                    orphan_by_hash.setdefault(key, []).append(storage)

            new_names = minio_names - indexed_names
            truly_new_names = []

            for name in new_names:
                obj = minio_map[name]
                md5 = obj.etag.strip('"') if obj.etag else None
                key = (obj.size, md5) if md5 else None

                if key and key in orphan_by_hash and orphan_by_hash[key]:
                    orphan_storage = orphan_by_hash[key].pop(0)
                    old_path = orphan_storage.object_key

                    try:
                        orphan_storage.object_key = name
                        orphan_storage.etag = md5 or ''
                        orphan_storage.size_bytes = obj.size or 0
                        orphan_storage.last_modified = obj.last_modified
                        orphan_storage.save(update_fields=['object_key', 'etag', 'size_bytes', 'last_modified', 'updated_at'])

                        existing_codes = list(
                            orphan_storage.document.employee_codes.values_list('employee_code', flat=True)
                        )
                        index_state = getattr(orphan_storage.document, 'index_state', None)
                        is_indexed = index_state.is_indexed if index_state else True

                        upsert_document_from_upload(
                            object_key=name,
                            metadata=extract_metadata(name),
                            size_bytes=obj.size or 0,
                            etag=md5,
                            last_modified=obj.last_modified,
                            employee_codes=existing_codes,
                            is_indexed=is_indexed,
                            actor=request.user,
                        )

                        if dual_write_legacy:
                            PDFIndex.objects.filter(minio_object_name=old_path).update(minio_object_name=name)

                        moved_files += 1
                        if len(moved_details) < 20:
                            moved_details.append({'old_path': old_path, 'new_path': name})

                        orphan_names.discard(old_path)
                    except Exception as move_error:
                        logger.error(f'✗ Error procesando archivo movido {name}: {move_error}')
                        errors += 1
                else:
                    truly_new_names.append(name)

            if orphan_names:
                for orphan_name in orphan_names:
                    try:
                        document = deactivate_document_by_storage_key(
                            object_key=orphan_name,
                            actor=request.user,
                        )
                        if document:
                            removed_orphans += 1
                    except Exception as orphan_error:
                        logger.error(f'✗ Error desactivando huérfano {orphan_name}: {orphan_error}')
                        errors += 1

                if dual_write_legacy:
                    PDFIndex.objects.filter(minio_object_name__in=orphan_names).delete()

            total_truly_new = len(truly_new_names)
            pending_new = total_truly_new

            if not skip_new and truly_new_names:
                batch = truly_new_names[:batch_size]
                for name in batch:
                    try:
                        obj = minio_map[name]
                        meta = extract_metadata(name)
                        text, codigos = extract_text_from_pdf(name)
                        md5_hash = obj.etag.strip('"') if obj.etag else None
                        is_indexed = bool(text)

                        upsert_document_from_upload(
                            object_key=name,
                            metadata=meta,
                            size_bytes=obj.size or 0,
                            etag=md5_hash,
                            last_modified=obj.last_modified,
                            employee_codes=codigos,
                            is_indexed=is_indexed,
                            actor=request.user,
                        )

                        if dual_write_legacy:
                            PDFIndex.objects.update_or_create(
                                minio_object_name=name,
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
                                    'is_indexed': is_indexed,
                                },
                            )

                        new_files += 1
                        pending_new -= 1
                    except Exception as index_error:
                        logger.error(f'✗ Error indexando {name}: {index_error}')
                        errors += 1
                        pending_new -= 1

            elapsed = round(time.time() - start_time, 2)
            has_more = pending_new > 0 and not skip_new

            if total_truly_new > 0:
                progress_percent = round(((total_truly_new - pending_new) / total_truly_new) * 100)
            else:
                progress_percent = 100

            result = {
                'message': 'Sincronización completada' if not has_more else f'Lote procesado ({new_files} de {total_truly_new})',
                'total_in_minio': len(minio_names),
                'total_indexed': Document.objects.filter(is_active=True, index_state__is_indexed=True).count(),
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

            record_audit_event(
                action='INDEX_SYNC_COMPLETED',
                resource_type='index',
                resource_id='docrepo_sync',
                request=request,
                actor=request.user,
                metadata=result,
            )

            status_log = 'parcial' if has_more else 'completa'
            logger.info(
                f"✓ Sincronización {status_log}: {new_files} nuevos, {moved_files} movidos, "
                f"{removed_orphans} desactivados, {pending_new} pendientes en {elapsed}s"
            )

            return Response(result)
        except Exception as e:
            logger.error(f'Error en sincronización: {e}')
            record_audit_event(
                action='INDEX_SYNC_FAILED',
                resource_type='index',
                resource_id='docrepo_sync',
                request=request,
                actor=request.user,
                metadata={'status_code': 500, 'error': str(e)},
            )
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
    permission_classes = [IsAdminUser]

    def post(self, request):
        import logging
        logger = logging.getLogger(__name__)

        data = request.data or {}
        batch_size = min(int(data.get('batch_size', 500)), 2000)
        dual_write_legacy = getattr(settings, 'DOCREPO_DUAL_WRITE_LEGACY_ENABLED', True)

        start_time = time.time()
        updated = 0
        legacy_updated = 0
        not_found = 0
        errors = 0

        try:
            minio_etags = {}
            for obj in minio_client.list_objects(settings.MINIO_BUCKET, recursive=True):
                if obj.object_name.endswith('.pdf') and obj.etag:
                    minio_etags[obj.object_name] = {
                        'hash': obj.etag.strip('"'),
                        'size': obj.size,
                        'last_modified': obj.last_modified,
                    }

            base_storage_qs = StorageObject.objects.select_related('document').filter(
                bucket_name=settings.MINIO_BUCKET,
                document__is_active=True,
            ).exclude(object_key='')

            total_without_hash = base_storage_qs.filter(
                Q(etag__isnull=True) | Q(etag='')
            ).count()

            if total_without_hash == 0:
                total_records = base_storage_qs.count()
                elapsed = round(time.time() - start_time, 2)
                result = {
                    'message': 'No hay registros pendientes de hash' if total_records > 0 else 'No hay PDFs indexados',
                    'updated': 0,
                    'legacy_updated': 0,
                    'not_found_in_minio': 0,
                    'pending': 0,
                    'has_more': False,
                    'progress_percent': 100,
                    'errors': 0,
                    'time_seconds': elapsed,
                    'batch_size': batch_size,
                    'total_records': total_records,
                    'source': 'docrepo_v2',
                }
                return Response(result)

            qs = base_storage_qs.filter(
                Q(etag__isnull=True) | Q(etag='')
            )[:batch_size]

            for storage in qs:
                if storage.object_key in minio_etags:
                    try:
                        info = minio_etags[storage.object_key]
                        storage.etag = info['hash']
                        storage.size_bytes = info['size']
                        storage.last_modified = info['last_modified']
                        storage.save(update_fields=['etag', 'size_bytes', 'last_modified', 'updated_at'])

                        document = storage.document
                        document.source_hash_md5 = info['hash']
                        document.save(update_fields=['source_hash_md5', 'updated_at'])

                        if dual_write_legacy:
                            legacy_updated += PDFIndex.objects.filter(
                                minio_object_name=storage.object_key
                            ).update(
                                md5_hash=info['hash'],
                                size_bytes=info['size'],
                                last_modified=info['last_modified'],
                            )

                        updated += 1
                    except Exception as e:
                        logger.error(f"Error actualizando hash de {storage.object_key}: {e}")
                        errors += 1
                else:
                    not_found += 1

            elapsed = round(time.time() - start_time, 2)
            pending = total_without_hash - updated
            has_more = pending > 0

            total_records = base_storage_qs.count()
            if total_records > 0:
                progress_percent = round(((total_records - pending) / total_records) * 100, 1)
            else:
                progress_percent = 100

            result = {
                'message': 'Hashes poblados' if not has_more else f'Lote procesado ({updated} de {total_without_hash})',
                'updated': updated,
                'legacy_updated': legacy_updated,
                'not_found_in_minio': not_found,
                'pending': pending,
                'has_more': has_more,
                'progress_percent': progress_percent,
                'errors': errors,
                'time_seconds': elapsed,
                'batch_size': batch_size,
                'source': 'docrepo_v2',
            }

            logger.info(f"✓ Populate hashes: {updated} actualizados, {pending} pendientes en {elapsed}s")

            record_audit_event(
                action='INDEX_HASH_POPULATE_COMPLETED',
                resource_type='index',
                resource_id='docrepo_hash_populate',
                request=request,
                actor=request.user,
                metadata=result,
            )

            return Response(result)

        except Exception as e:
            logger.error(f"Error en populate hashes: {e}")
            record_audit_event(
                action='INDEX_HASH_POPULATE_FAILED',
                resource_type='index',
                resource_id='docrepo_hash_populate',
                request=request,
                actor=request.user,
                metadata={'status_code': 500, 'error': str(e)},
            )
            return Response({'error': f'Error inesperado: {str(e)}'}, status=500)

class IndexStatsView(APIView):
    """
    Estadísticas del índice de PDFs.
    GET /api/index/stats
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        documents_qs = Document.objects.filter(is_active=True)
        total = documents_qs.count()

        total_size = StorageObject.objects.filter(
            bucket_name=settings.MINIO_BUCKET,
            document__is_active=True,
        ).aggregate(Sum('size_bytes'))['size_bytes__sum'] or 0

        last = documents_qs.order_by('-indexed_at').first() if total > 0 else None

        by_year = {
            str(row['period__year']): row['c']
            for row in documents_qs.exclude(period__isnull=True)
            .values('period__year')
            .annotate(c=Count('id'))
            if row['period__year'] is not None
        }
        by_razon_social = {
            row['company__name']: row['c']
            for row in documents_qs.values('company__name').annotate(c=Count('id'))
            if row['company__name']
        }
        by_banco = {
            row['constancia_detail__bank__name']: row['c']
            for row in documents_qs.exclude(constancia_detail__bank__name__isnull=True)
            .exclude(constancia_detail__bank__name='')
            .values('constancia_detail__bank__name')
            .annotate(c=Count('id'))
        }

        return Response({
            'total_indexed': total,
            'total_size_gb': round(total_size / (1024**3), 2),
            'by_year': by_year,
            'by_razon_social': by_razon_social,
            'by_banco': by_banco,
            'last_indexed': last.indexed_at.isoformat() if last and last.indexed_at else None,
            'indexed_successfully': documents_qs.filter(index_state__is_indexed=True).count(),
            'with_errors': documents_qs.filter(Q(index_state__isnull=True) | Q(index_state__is_indexed=False)).count(),
            'source': 'docrepo_v2',
        })

class ReindexView(APIView):
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
        dual_write_legacy = getattr(settings, 'DOCREPO_DUAL_WRITE_LEGACY_ENABLED', True)

        start_time = time.time()
        indexed_count = 0
        new_count = 0
        updated_count = 0
        error_count = 0
        orphans_removed = 0

        try:
            minio_objects = {}
            for obj in minio_client.list_objects(settings.MINIO_BUCKET, recursive=True):
                if obj.object_name.endswith('.pdf'):
                    minio_objects[obj.object_name] = obj

            logger.info(f'📁 Encontrados {len(minio_objects)} PDFs en MinIO')

            minio_keys = set(minio_objects.keys())
            storage_rows = StorageObject.objects.select_related('document').filter(
                bucket_name=settings.MINIO_BUCKET,
                document__is_active=True,
            )
            storage_by_key = {row.object_key: row for row in storage_rows if row.object_key}
            indexed_keys = set(storage_by_key.keys())

            if clean_orphans:
                orphan_names = indexed_keys - minio_keys
                for orphan_name in orphan_names:
                    try:
                        document = deactivate_document_by_storage_key(
                            object_key=orphan_name,
                            actor=request.user,
                        )
                        if document:
                            orphans_removed += 1
                    except Exception as orphan_error:
                        error_count += 1
                        logger.error(f'✗ Error desactivando huérfano {orphan_name}: {orphan_error}')

                if dual_write_legacy and orphan_names:
                    PDFIndex.objects.filter(minio_object_name__in=orphan_names).delete()

            to_process = []
            for object_name, obj in minio_objects.items():
                try:
                    existing = storage_by_key.get(object_name)
                    if existing is None:
                        to_process.append((obj, 'new'))
                        new_count += 1
                        continue

                    existing_md5 = (existing.etag or '').strip('"')
                    current_md5 = obj.etag.strip('"') if obj.etag else ''
                    changed = (
                        existing.last_modified != obj.last_modified
                        or (existing.size_bytes or 0) != (obj.size or 0)
                        or existing_md5 != current_md5
                    )

                    if changed:
                        to_process.append((obj, 'update'))
                        updated_count += 1
                    else:
                        indexed_count += 1
                except Exception as classify_error:
                    error_count += 1
                    logger.error(f'✗ Error clasificando {object_name}: {classify_error}')

            for obj, action in to_process:
                try:
                    meta = extract_metadata(obj.object_name)
                    text, codigos = extract_text_from_pdf(obj.object_name)
                    md5_hash = obj.etag.strip('"') if obj.etag else None
                    is_indexed = bool(text)

                    upsert_document_from_upload(
                        object_key=obj.object_name,
                        metadata=meta,
                        size_bytes=obj.size or 0,
                        etag=md5_hash,
                        last_modified=obj.last_modified,
                        employee_codes=codigos,
                        is_indexed=is_indexed,
                        actor=request.user,
                    )

                    if dual_write_legacy:
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
                                'is_indexed': is_indexed,
                            },
                        )

                    indexed_count += 1
                except Exception as e:
                    error_count += 1
                    logger.error(f'✗ Error indexando {obj.object_name}: {e}')

            elapsed = round(time.time() - start_time, 2)
            result = {
                'message': 'Indexación completada',
                'total_in_minio': len(minio_objects),
                'total_indexed': indexed_count,
                'new_indexed': new_count,
                'updated': updated_count,
                'orphans_removed': orphans_removed,
                'errors': error_count,
                'time_seconds': elapsed,
            }

            logger.info(f'✓ Indexación completada: {indexed_count} PDFs en {elapsed}s')
            record_audit_event(
                action='INDEX_REINDEX_COMPLETED',
                resource_type='index',
                resource_id='docrepo_reindex',
                request=request,
                actor=request.user,
                metadata=result,
            )
            return Response(result)
        except Exception as e:
            logger.error(f'Error en reindexación: {e}')
            record_audit_event(
                action='INDEX_REINDEX_FAILED',
                resource_type='index',
                resource_id='docrepo_reindex',
                request=request,
                actor=request.user,
                metadata={'status_code': 500, 'error': str(e)},
            )
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
        def safe_int(value, default=None):
            try:
                return int(str(value).strip())
            except (TypeError, ValueError):
                return default

        def resolve_tipo_documento(doc):
            if getattr(doc, 'domain_id', None) is None:
                return ''

            domain_code = getattr(getattr(doc, 'domain', None), 'code', '')
            if domain_code == 'CONSTANCIA_ABONO':
                constancia = getattr(doc, 'constancia_detail', None)
                if constancia is None:
                    return ''
                return constancia.payroll_type or constancia.legacy_tipo_documento or ''
            if domain_code == 'SEGUROS':
                insurance = getattr(doc, 'insurance_detail', None)
                if insurance is None or insurance.insurance_type is None:
                    return ''
                if insurance.insurance_subtype is not None:
                    return f"{insurance.insurance_type.name} - {insurance.insurance_subtype.name}"
                return insurance.insurance_type.name
            if domain_code == 'TREGISTRO':
                treg = getattr(doc, 'tregistro_detail', None)
                if treg is None or treg.movement_type is None:
                    return ''
                return treg.movement_type.name
            return ''

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
            query = Q(is_active=True, index_state__is_indexed=True)

            if folder_filter:
                query &= Q(storage_object__object_key__startswith=folder_filter)
            if search_query:
                query &= Q(storage_object__object_key__icontains=search_query)
            if año:
                year_value = safe_int(año)
                if year_value is not None:
                    query &= Q(period__year=year_value)
            if mes:
                month_value = safe_int(mes)
                if month_value is not None:
                    query &= Q(period__month=month_value)
            if banco:
                query &= Q(constancia_detail__bank__name__iexact=banco) | Q(constancia_detail__bank__code__iexact=banco)
            if razon_social:
                query &= Q(company__name__iexact=razon_social) | Q(company__code__iexact=razon_social)
            if tipo_documento:
                query &= (
                    Q(constancia_detail__payroll_type__icontains=tipo_documento)
                    | Q(constancia_detail__legacy_tipo_documento__icontains=tipo_documento)
                    | Q(insurance_detail__insurance_type__name__icontains=tipo_documento)
                    | Q(insurance_detail__insurance_subtype__name__icontains=tipo_documento)
                    | Q(tregistro_detail__movement_type__name__icontains=tipo_documento)
                )

            # Ordenamiento
            order_prefix = '' if order == 'asc' else '-'
            field_map = {
                'indexed_at': 'indexed_at',
                'last_modified': 'storage_object__last_modified',
                'size': 'storage_object__size_bytes',
                'filename': 'storage_object__object_key'
            }
            order_field = field_map.get(sort_field, 'indexed_at')
            ordering = f'{order_prefix}{order_field}'

            queryset = Document.objects.filter(query).select_related(
                'domain',
                'company',
                'period',
                'storage_object',
                'index_state',
                'constancia_detail__bank',
                'insurance_detail__insurance_type',
                'insurance_detail__insurance_subtype',
                'tregistro_detail__movement_type',
            ).order_by(ordering)
            total = queryset.count()

            # Paginación manual
            start = (page - 1) * per_page
            end = start + per_page
            paginated = queryset[start:end]

            total_pages = (total + per_page - 1) // per_page

            files = []
            for record in paginated:
                storage = getattr(record, 'storage_object', None)
                object_key = storage.object_key if storage and storage.object_key else record.source_path_legacy
                size_bytes = storage.size_bytes if storage and storage.size_bytes else 0
                if size_bytes < 1024:
                    size_human = f"{size_bytes} B"
                elif size_bytes < 1024 * 1024:
                    size_human = f"{size_bytes / 1024:.1f} KB"
                else:
                    size_human = f"{size_bytes / (1024 * 1024):.1f} MB"

                parts = object_key.split('/') if object_key else ['']
                file_name = parts[-1]
                folder_name = '/'.join(parts[:-1]) if len(parts) > 1 else ''
                index_state = getattr(record, 'index_state', None)
                constancia = getattr(record, 'constancia_detail', None)
                period = getattr(record, 'period', None)

                files.append({
                    'name': file_name,
                    'path': object_key,
                    'folder': folder_name,
                    'size_bytes': size_bytes,
                    'size_human': size_human,
                    'last_modified': storage.last_modified.isoformat() if storage and storage.last_modified else None,
                    'indexed_at': record.indexed_at.isoformat() if record.indexed_at else None,
                    'indexed': index_state.is_indexed if index_state else False,
                    'año': str(period.year) if period else '',
                    'mes': f"{period.month:02d}" if period else '',
                    'banco': constancia.bank.name if constancia and constancia.bank else '',
                    'razon_social': record.company.name if record.company else '',
                    'tipo_documento': resolve_tipo_documento(record),
                    'download_url': f'/api/download/{object_key}' if object_key else None,
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


class FilesClassifyPreviewView(APIView):
    """
    Previsualiza clasificación automática y ruta lógica sin guardar en MinIO.
    POST /api/files/classify-preview (multipart/form-data)
    """

    permission_classes = [IsAdminUser]

    def post(self, request):
        import logging
        logger = logging.getLogger(__name__)

        files = request.FILES.getlist('files[]')
        if not files:
            return Response({'error': 'No se proporcionaron archivos.'}, status=400)

        hints = _build_upload_hints(request)
        min_confidence = float(getattr(settings, 'DOCREPO_CLASSIFICATION_MIN_CONFIDENCE', 0.7))

        items = []
        ready = 0
        requires_confirmation = 0
        duplicates = 0

        for file in files:
            if not file or not file.name:
                continue

            if not file.name.lower().endswith('.pdf'):
                items.append({
                    'filename': file.name,
                    'status': 'INVALID_FILE',
                    'requires_confirmation': True,
                    'warnings': ['invalid_extension'],
                    'missing_fields': [],
                    'duplicate': None,
                })
                requires_confirmation += 1
                continue

            try:
                file_content = file.read()
                file_size = len(file_content)
                file_md5 = hashlib.md5(file_content).hexdigest()

                preview_text, preview_codes = extract_text_from_pdf_bytes(file_content)
                meta = infer_upload_metadata(file.name, preview_text, hints)
                domain_code = meta.get('domain_code', 'CONSTANCIA_ABONO')
                logical_prefix = build_auto_storage_prefix(meta, domain_code)
                logical_path = f"{logical_prefix}/{file.name}"

                duplicate = _find_active_duplicate_by_hash_size(file_size, file_md5)
                if duplicate is not None:
                    duplicates += 1

                missing_fields = _classification_missing_fields(meta, domain_code)
                confidence = _classification_confidence(meta, hints, preview_text, file.name)
                warnings = _classification_warnings(meta, domain_code, confidence, duplicate, missing_fields)

                needs_confirmation = bool(
                    duplicate is not None
                    or missing_fields
                    or confidence < min_confidence
                )

                if duplicate is not None:
                    status = 'DUPLICATE'
                elif needs_confirmation:
                    status = 'REQUIRES_CONFIRMATION'
                else:
                    status = 'READY'

                if needs_confirmation:
                    requires_confirmation += 1
                else:
                    ready += 1

                items.append({
                    'filename': file.name,
                    'size': file_size,
                    'md5': file_md5,
                    'status': status,
                    'requires_confirmation': needs_confirmation,
                    'confidence': confidence,
                    'domain': domain_code,
                    'metadata': {
                        'año': meta.get('año', ''),
                        'mes': meta.get('mes', ''),
                        'razon_social': meta.get('razon_social', ''),
                        'banco': meta.get('banco', ''),
                        'tipo_documento': meta.get('tipo_documento', ''),
                    },
                    'logical_prefix': logical_prefix,
                    'logical_path': logical_path,
                    'missing_fields': missing_fields,
                    'warnings': warnings,
                    'detected_codes_count': len(preview_codes or []),
                    'duplicate': {
                        'document_id': str(duplicate.document.id),
                        'object_key': duplicate.object_key,
                    } if duplicate is not None else None,
                })
            except Exception as preview_error:
                logger.error(f'✗ Error preclasificando {file.name}: {preview_error}')
                requires_confirmation += 1
                items.append({
                    'filename': file.name,
                    'status': 'ERROR',
                    'requires_confirmation': True,
                    'warnings': ['preview_error'],
                    'missing_fields': [],
                    'error': str(preview_error),
                    'duplicate': None,
                })

        summary = {
            'total_files': len(items),
            'ready': ready,
            'requires_confirmation': requires_confirmation,
            'duplicates': duplicates,
            'min_confidence': min_confidence,
        }

        record_audit_event(
            action='FILE_CLASSIFICATION_PREVIEWED',
            resource_type='file',
            resource_id='bulk_preview',
            request=request,
            actor=request.user,
            metadata=summary,
        )

        return Response({
            'success': True,
            'summary': summary,
            'files': items,
        })


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
        dual_write_legacy = getattr(settings, 'DOCREPO_DUAL_WRITE_LEGACY_ENABLED', True)
        auto_route_enabled = getattr(settings, 'DOCREPO_AUTO_ROUTE_UPLOAD_ENABLED', True)

        files = request.FILES.getlist('files[]')
        requested_folder = request.POST.get('folder', '').strip()

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
                # Leer contenido del archivo
                file_content = file.read()
                file_size = len(file_content)
                file_md5 = hashlib.md5(file_content).hexdigest()

                duplicate = _find_active_duplicate_by_hash_size(file_size, file_md5)
                if duplicate is not None:
                    record_audit_event(
                        action='FILE_UPLOAD_DUPLICATE_BLOCKED',
                        resource_type='file',
                        resource_id=file.name,
                        request=request,
                        actor=request.user,
                        document=duplicate.document,
                        metadata={
                            'status_code': 409,
                            'filename': file.name,
                            'size_bytes': file_size,
                            'md5_hash': file_md5,
                            'existing_document_id': str(duplicate.document.id),
                            'existing_object_key': duplicate.object_key,
                        },
                    )
                    errors.append({
                        'filename': file.name,
                        'error': 'Archivo duplicado detectado (mismo hash y tamaño).',
                        'code': 'DUPLICATE_FILE',
                        'existing_document_id': str(duplicate.document.id),
                        'existing_path': duplicate.object_key,
                    })
                    continue

                hints = _build_upload_hints(request)

                auto_routed = False
                preview_domain = ''
                normalized_folder = requested_folder
                preview_text = None
                preview_codes = []

                if normalized_folder:
                    if not normalized_folder.endswith('/'):
                        normalized_folder += '/'
                    object_name = f"{normalized_folder}{file.name}"
                    meta = extract_metadata(object_name)
                elif auto_route_enabled:
                    preview_text, preview_codes = extract_text_from_pdf_bytes(file_content)
                    meta = infer_upload_metadata(file.name, preview_text, hints)
                    preview_domain = meta.get('domain_code', '')
                    auto_prefix = build_auto_storage_prefix(meta, preview_domain)
                    object_name = f"{auto_prefix}/{file.name}"
                    auto_routed = True
                else:
                    object_name = file.name
                    meta = extract_metadata(object_name)

                # Subir a MinIO
                minio_client.put_object(
                    settings.MINIO_BUCKET,
                    object_name,
                    BytesIO(file_content),
                    length=file_size,
                    content_type='application/pdf'
                )

                logger.info(f"✓ Archivo subido: {object_name}")

                stat = minio_client.stat_object(settings.MINIO_BUCKET, object_name)
                object_etag = stat.etag.strip('"') if getattr(stat, 'etag', None) else file_md5
                object_last_modified = getattr(stat, 'last_modified', None)

                if auto_routed and preview_text is not None:
                    text, codigos = preview_text, preview_codes
                else:
                    text, codigos = extract_text_from_pdf(object_name)
                indexed = bool(text)

                ingest_result = upsert_document_from_upload(
                    object_key=object_name,
                    metadata=meta,
                    size_bytes=file_size,
                    etag=object_etag,
                    last_modified=object_last_modified,
                    employee_codes=codigos,
                    is_indexed=indexed,
                    actor=request.user,
                )

                legacy_synced = False
                legacy_sync_error = ''
                if dual_write_legacy:
                    try:
                        PDFIndex.objects.update_or_create(
                            minio_object_name=object_name,
                            defaults={
                                'razon_social': meta['razon_social'],
                                'banco': meta['banco'],
                                'mes': meta['mes'],
                                'año': meta['año'],
                                'tipo_documento': meta['tipo_documento'],
                                'size_bytes': file_size,
                                'md5_hash': object_etag,
                                'codigos_empleado': ','.join(codigos) if codigos else '',
                                'last_modified': object_last_modified,
                                'is_indexed': indexed,
                            }
                        )
                        legacy_synced = True
                    except Exception as legacy_error:
                        legacy_sync_error = str(legacy_error)
                        logger.warning(f"Legacy mirror sync failed for {object_name}: {legacy_error}")

                record_audit_event(
                    action='FILE_UPLOAD_SUCCEEDED',
                    resource_type='file',
                    resource_id=object_name,
                    request=request,
                    actor=request.user,
                    document=ingest_result.document,
                    metadata={
                        'status_code': 201,
                        'object_key': object_name,
                        'domain': ingest_result.domain_code,
                        'domain_preview': preview_domain,
                        'auto_routed': auto_routed,
                        'requested_folder': requested_folder,
                        'md5_hash': file_md5,
                        'indexed': indexed,
                        'size_bytes': file_size,
                        'legacy_sync_enabled': dual_write_legacy,
                        'legacy_synced': legacy_synced,
                        'legacy_sync_error': legacy_sync_error,
                    },
                )

                uploaded.append({
                    'filename': file.name,
                    'path': object_name,
                    'size': file_size,
                    'indexed': indexed,
                    'docrepo_document_id': str(ingest_result.document.id),
                    'domain': ingest_result.domain_code,
                    'domain_preview': preview_domain,
                    'auto_routed': auto_routed,
                    'md5_hash': file_md5,
                    'legacy_sync_enabled': dual_write_legacy,
                    'legacy_synced': legacy_synced,
                    'legacy_sync_error': legacy_sync_error,
                })

            except Exception as e:
                logger.error(f"✗ Error subiendo {file.name}: {e}")
                record_audit_event(
                    action='FILE_UPLOAD_FAILED',
                    resource_type='file',
                    resource_id=file.name,
                    request=request,
                    actor=request.user,
                    metadata={
                        'status_code': 500,
                        'filename': file.name,
                        'error': str(e),
                    },
                )
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
            legacy_deleted_count, _ = PDFIndex.objects.filter(minio_object_name=file_path).delete()
            logger.info(f"✓ Índice eliminado de PostgreSQL: {file_path}")

            document = deactivate_document_by_storage_key(
                object_key=file_path,
                actor=request.user,
            )

            record_audit_event(
                action='FILE_DELETE_SUCCEEDED',
                resource_type='file',
                resource_id=file_path,
                request=request,
                actor=request.user,
                document=document,
                metadata={
                    'status_code': 200,
                    'object_key': file_path,
                    'legacy_deleted_count': legacy_deleted_count,
                    'docrepo_document_id': str(document.id) if document else None,
                },
            )

            return Response({
                'success': True,
                'message': 'Archivo eliminado correctamente',
                'path': file_path,
                'legacy_deleted_count': legacy_deleted_count,
                'docrepo_document_id': str(document.id) if document else None,
            })

        except S3Error as e:
            if e.code == 'NoSuchKey':
                # El archivo no existe en MinIO, pero limpiar índice
                legacy_deleted_count, _ = PDFIndex.objects.filter(minio_object_name=file_path).delete()
                document = deactivate_document_by_storage_key(
                    object_key=file_path,
                    actor=request.user,
                )

                record_audit_event(
                    action='FILE_DELETE_NOT_FOUND',
                    resource_type='file',
                    resource_id=file_path,
                    request=request,
                    actor=request.user,
                    document=document,
                    metadata={
                        'status_code': 404,
                        'object_key': file_path,
                        'legacy_deleted_count': legacy_deleted_count,
                        'docrepo_document_id': str(document.id) if document else None,
                        'reason': 'minio_object_missing',
                    },
                )

                return Response({
                    'error': 'El archivo no existe en MinIO.',
                    'legacy_deleted_count': legacy_deleted_count,
                    'docrepo_document_id': str(document.id) if document else None,
                }, status=404)
            else:
                logger.error(f"✗ Error S3 eliminando {file_path}: {e}")
                record_audit_event(
                    action='FILE_DELETE_FAILED',
                    resource_type='file',
                    resource_id=file_path,
                    request=request,
                    actor=request.user,
                    metadata={
                        'status_code': 500,
                        'object_key': file_path,
                        'error': str(e),
                    },
                )
                return Response({'error': f'Error en MinIO: {str(e)}'}, status=500)
        except Exception as e:
            logger.error(f"✗ Error eliminando {file_path}: {e}")
            record_audit_event(
                action='FILE_DELETE_FAILED',
                resource_type='file',
                resource_id=file_path,
                request=request,
                actor=request.user,
                metadata={
                    'status_code': 500,
                    'object_key': file_path,
                    'error': str(e),
                },
            )
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
                paths = Document.objects.filter(
                    is_active=True,
                    index_state__is_indexed=True,
                    storage_object__object_key__startswith=parent,
                ).values_list('storage_object__object_key', flat=True)
            else:
                paths = Document.objects.filter(
                    is_active=True,
                    index_state__is_indexed=True,
                ).values_list('storage_object__object_key', flat=True)

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
    throttle_classes = [BulkSearchRateThrottle]

    def post(self, request):
        import logging
        logger = logging.getLogger(__name__)

        def safe_int(value, default=None):
            try:
                return int(str(value).strip())
            except (TypeError, ValueError):
                return default

        def resolve_tipo_documento(doc):
            domain_code = getattr(getattr(doc, 'domain', None), 'code', '')
            if domain_code == 'CONSTANCIA_ABONO':
                constancia = getattr(doc, 'constancia_detail', None)
                if constancia is None:
                    return ''
                return constancia.payroll_type or constancia.legacy_tipo_documento or ''
            if domain_code == 'SEGUROS':
                insurance = getattr(doc, 'insurance_detail', None)
                if insurance is None or insurance.insurance_type is None:
                    return ''
                if insurance.insurance_subtype is not None:
                    return f"{insurance.insurance_type.name} - {insurance.insurance_subtype.name}"
                return insurance.insurance_type.name
            if domain_code == 'TREGISTRO':
                treg = getattr(doc, 'tregistro_detail', None)
                if treg is None or treg.movement_type is None:
                    return ''
                return treg.movement_type.name
            return ''
        
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
            query = Q(is_active=True, index_state__is_indexed=True)
            
            # Aplicar filtros adicionales
            if año:
                year_value = safe_int(año)
                if year_value is not None:
                    query &= Q(period__year=year_value)
            if mes:
                month_value = safe_int(mes)
                if month_value is not None:
                    query &= Q(period__month=month_value)
            if banco:
                query &= Q(constancia_detail__bank__name__iexact=banco) | Q(constancia_detail__bank__code__iexact=banco)
            if razon_social:
                query &= Q(company__name__iexact=razon_social) | Q(company__code__iexact=razon_social)
            if tipo_documento:
                query &= (
                    Q(constancia_detail__payroll_type__icontains=tipo_documento)
                    | Q(constancia_detail__legacy_tipo_documento__icontains=tipo_documento)
                    | Q(insurance_detail__insurance_type__name__icontains=tipo_documento)
                    | Q(insurance_detail__insurance_subtype__name__icontains=tipo_documento)
                    | Q(tregistro_detail__movement_type__name__icontains=tipo_documento)
                )
            
            # Construir condiciones OR para todos los códigos
            query &= Q(employee_codes__employee_code__in=codigos)
            
            # Ejecutar consulta
            all_records = Document.objects.filter(query).select_related(
                'domain',
                'company',
                'period',
                'storage_object',
                'constancia_detail__bank',
                'insurance_detail__insurance_type',
                'insurance_detail__insurance_subtype',
                'tregistro_detail__movement_type',
            ).prefetch_related('employee_codes').distinct()
            
            logger.info(f"Búsqueda masiva: {len(codigos)} códigos → {all_records.count()} registros")
            
            # Procesar resultados
            results = []
            codigos_encontrados = set()
            
            for record in all_records:
                codes_in_document = {
                    code.employee_code
                    for code in record.employee_codes.all()
                    if code.employee_code
                }
                codigos_match = [codigo for codigo in codigos if codigo in codes_in_document]
                for code in codigos_match:
                    codigos_encontrados.add(code)
                
                if codigos_match:
                    storage = getattr(record, 'storage_object', None)
                    object_key = storage.object_key if storage and storage.object_key else record.source_path_legacy
                    size_bytes = storage.size_bytes if storage and storage.size_bytes else 0
                    period = getattr(record, 'period', None)
                    constancia = getattr(record, 'constancia_detail', None)

                    results.append({
                        'id': str(record.id),
                        'filename': object_key,
                        'metadata': {
                            'año': str(period.year) if period else '',
                            'mes': f"{period.month:02d}" if period else '',
                            'banco': constancia.bank.name if constancia and constancia.bank else '',
                            'razon_social': record.company.name if record.company else '',
                            'tipo_documento': resolve_tipo_documento(record)
                        },
                        'size_bytes': size_bytes,
                        'size_kb': round(size_bytes / 1024, 1),
                        'download_url': f'/api/download/{object_key}' if object_key else None,
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