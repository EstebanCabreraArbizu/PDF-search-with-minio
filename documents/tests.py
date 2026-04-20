from types import SimpleNamespace
from datetime import datetime
from unittest import TestCase
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from documents.views import (
	BulkSearchView,
	FilesClassifyPreviewView,
	FilesDeleteView,
	FilesListView,
	FilesUploadView,
	FoldersListView,
	IndexStatsView,
	PopulateHashesView,
	ReindexView,
	SyncIndexView,
)


class SearchViewFallbackTests(APITestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_user(
			username='search_tester',
			password='safe-password-123',
		)
		self.client.force_authenticate(user=self.user)

	@patch('documents.views.search_in_pdf')
	@patch('documents.views.minio_client.list_objects')
	def test_fallback_returns_single_result_without_duplicates(self, mock_list_objects, mock_search_in_pdf):
		fake_obj = SimpleNamespace(
			object_name='2025/RESGUARDO/01.ENERO/BCP/planilla_unica.pdf',
			size=2048,
		)
		mock_list_objects.return_value = [fake_obj]
		mock_search_in_pdf.return_value = True

		response = self.client.post(
			'/api/search',
			{
				'codigo_empleado': '12345678',
				'use_index': False,
			},
			format='json',
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['source'], 'minio_direct')
		self.assertEqual(response.data['total'], 1)
		self.assertEqual(len(response.data['results']), 1)
		self.assertEqual(response.data['results'][0]['filename'], fake_obj.object_name)
		self.assertIn('search_time_ms', response.data)

		# Regression guard: each object must be evaluated only once.
		self.assertEqual(mock_search_in_pdf.call_count, 1)

	@patch('documents.views.search_in_pdf')
	@patch('documents.views.minio_client.list_objects')
	def test_fallback_applies_filters_and_returns_empty_when_bank_mismatch(self, mock_list_objects, mock_search_in_pdf):
		fake_obj = SimpleNamespace(
			object_name='2025/RESGUARDO/01.ENERO/BCP/planilla_filtrada.pdf',
			size=4096,
		)
		mock_list_objects.return_value = [fake_obj]
		mock_search_in_pdf.return_value = True

		response = self.client.post(
			'/api/search',
			{
				'codigo_empleado': '12345678',
				'use_index': False,
				'banco': 'BBVA',
			},
			format='json',
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['source'], 'minio_direct')
		self.assertEqual(response.data['total'], 0)
		self.assertEqual(response.data['results'], [])
		self.assertEqual(mock_search_in_pdf.call_count, 0)


class DocrepoIndexViewsUnitTests(TestCase):
	def setUp(self):
		self.admin_user = SimpleNamespace(
			id=999,
			is_authenticated=True,
			is_staff=True,
		)

		from documents import views
		views._minio_list_cache = {'time': 0, 'data': None}

	def _request(self, data=None):
		return SimpleNamespace(
			data=data or {},
			user=self.admin_user,
			META={},
		)

	@patch('documents.views.StorageObject.objects.select_related')
	@patch('documents.views.Document.objects.filter')
	@patch('documents.views.minio_client.list_objects')
	def test_sync_returns_empty_payload_when_minio_and_index_are_empty(
		self,
		mock_list_objects,
		mock_document_filter,
		mock_select_related,
	):
		mock_list_objects.return_value = []
		mock_document_filter.return_value = SimpleNamespace(count=lambda: 0)

		storage_qs = MagicMock()
		storage_qs.filter.return_value = []
		mock_select_related.return_value = storage_qs

		response = SyncIndexView().post(self._request({'batch_size': 10}))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['total_in_minio'], 0)
		self.assertEqual(response.data['total_indexed'], 0)
		self.assertEqual(response.data['new_files'], 0)
		self.assertEqual(response.data['moved_files'], 0)
		self.assertEqual(response.data['removed_orphans'], 0)

	@patch('documents.views.record_audit_event')
	@patch('documents.views.upsert_document_from_upload')
	@patch('documents.views.extract_text_from_pdf')
	@patch('documents.views.extract_metadata')
	@patch('documents.views.StorageObject.objects.select_related')
	@patch('documents.views.minio_client.list_objects')
	@patch('documents.views.settings.DOCREPO_DUAL_WRITE_LEGACY_ENABLED', False)
	def test_reindex_indexes_new_pdf_in_docrepo_flow(
		self,
		mock_list_objects,
		mock_select_related,
		mock_extract_metadata,
		mock_extract_text,
		mock_upsert,
		mock_record_audit,
	):
		fake_obj = SimpleNamespace(
			object_name='2025/RESGUARDO/01.ENERO/BCP/archivo_nuevo.pdf',
			size=1024,
			etag='"abc123"',
			last_modified=datetime.utcnow(),
		)
		mock_list_objects.return_value = [fake_obj]

		storage_qs = MagicMock()
		storage_qs.filter.return_value = []
		mock_select_related.return_value = storage_qs

		mock_extract_metadata.return_value = {
			'año': '2025',
			'razon_social': 'RESGUARDO',
			'mes': '01',
			'banco': 'BCP',
			'tipo_documento': 'GENERAL',
		}
		mock_extract_text.return_value = ('contenido', ['12345678'])

		response = ReindexView().post(self._request({'clean_orphans': True}))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['total_in_minio'], 1)
		self.assertEqual(response.data['new_indexed'], 1)
		self.assertEqual(response.data['updated'], 0)
		self.assertEqual(response.data['errors'], 0)
		self.assertEqual(response.data['total_indexed'], 1)

		mock_upsert.assert_called_once()
		self.assertTrue(mock_record_audit.called)

	@patch('documents.views.settings.DOCREPO_DUAL_WRITE_LEGACY_ENABLED', False)
	@patch('documents.views.record_audit_event')
	@patch('documents.views.StorageObject.objects.select_related')
	@patch('documents.views.minio_client.list_objects')
	def test_populate_hashes_returns_no_pending_when_already_complete(
		self,
		mock_list_objects,
		mock_select_related,
		mock_record_audit,
	):
		mock_list_objects.return_value = []

		base_storage_qs = MagicMock()
		pending_qs = MagicMock()
		pending_qs.count.return_value = 0

		filter_qs = MagicMock()
		filter_qs.exclude.return_value = base_storage_qs

		mock_select_related.return_value.filter.return_value = filter_qs
		base_storage_qs.filter.return_value = pending_qs
		base_storage_qs.count.return_value = 2

		response = PopulateHashesView().post(self._request({'batch_size': 50}))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['updated'], 0)
		self.assertEqual(response.data['pending'], 0)
		self.assertEqual(response.data['has_more'], False)
		self.assertEqual(response.data['source'], 'docrepo_v2')
		self.assertEqual(response.data['total_records'], 2)
		self.assertFalse(mock_record_audit.called)

	@patch('documents.views.settings.DOCREPO_DUAL_WRITE_LEGACY_ENABLED', False)
	@patch('documents.views.record_audit_event')
	@patch('documents.views.StorageObject.objects.select_related')
	@patch('documents.views.minio_client.list_objects')
	def test_populate_hashes_updates_storage_and_document_hash(
		self,
		mock_list_objects,
		mock_select_related,
		mock_record_audit,
	):
		fake_obj = SimpleNamespace(
			object_name='2025/RESGUARDO/01.ENERO/BCP/hash_target.pdf',
			etag='"etag-hash"',
			size=2048,
			last_modified=datetime.utcnow(),
		)
		mock_list_objects.return_value = [fake_obj]

		storage_obj = MagicMock()
		storage_obj.object_key = fake_obj.object_name
		storage_obj.document = MagicMock()

		pending_qs = MagicMock()
		pending_qs.count.return_value = 1
		pending_qs.__getitem__.return_value = [storage_obj]

		base_storage_qs = MagicMock()
		base_storage_qs.filter.side_effect = [pending_qs, pending_qs]
		base_storage_qs.count.return_value = 1

		filter_qs = MagicMock()
		filter_qs.exclude.return_value = base_storage_qs
		mock_select_related.return_value.filter.return_value = filter_qs

		response = PopulateHashesView().post(self._request({'batch_size': 50}))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['updated'], 1)
		self.assertEqual(response.data['legacy_updated'], 0)
		self.assertEqual(response.data['errors'], 0)
		self.assertEqual(response.data['source'], 'docrepo_v2')

		storage_obj.save.assert_called_once()
		storage_obj.document.save.assert_called_once()
		mock_record_audit.assert_called_once()

	@patch('documents.views.StorageObject.objects.filter')
	@patch('documents.views.Document.objects.filter')
	def test_index_stats_returns_docrepo_aggregated_payload(
		self,
		mock_document_filter,
		mock_storage_filter,
	):
		last = SimpleNamespace(indexed_at=datetime(2026, 4, 20, 12, 0, 0))

		documents_qs = MagicMock()
		documents_qs.count.return_value = 4
		documents_qs.order_by.return_value.first.return_value = last

		year_qs = MagicMock()
		year_qs.values.return_value.annotate.return_value = [
			{'period__year': 2025, 'c': 3},
			{'period__year': 2024, 'c': 1},
		]

		bank_qs = MagicMock()
		bank_qs.exclude.return_value.values.return_value.annotate.return_value = [
			{'constancia_detail__bank__name': 'BCP', 'c': 2},
		]

		documents_qs.exclude.side_effect = [year_qs, bank_qs]

		company_values_qs = MagicMock()
		company_values_qs.annotate.return_value = [
			{'company__name': 'RESGUARDO', 'c': 4},
		]
		documents_qs.values.return_value = company_values_qs

		documents_qs.filter.side_effect = [
			SimpleNamespace(count=lambda: 3),
			SimpleNamespace(count=lambda: 1),
		]

		mock_document_filter.return_value = documents_qs

		storage_qs = MagicMock()
		storage_qs.aggregate.return_value = {'size_bytes__sum': 1024**3}
		mock_storage_filter.return_value = storage_qs

		response = IndexStatsView().get(self._request())

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['source'], 'docrepo_v2')
		self.assertEqual(response.data['total_indexed'], 4)
		self.assertEqual(response.data['total_size_gb'], 1.0)
		self.assertEqual(response.data['by_year'], {'2025': 3, '2024': 1})
		self.assertEqual(response.data['by_razon_social'], {'RESGUARDO': 4})
		self.assertEqual(response.data['by_banco'], {'BCP': 2})
		self.assertEqual(response.data['indexed_successfully'], 3)
		self.assertEqual(response.data['with_errors'], 1)


class DocrepoFileManagementViewsUnitTests(TestCase):
	def setUp(self):
		self.admin_user = SimpleNamespace(
			id=1001,
			is_authenticated=True,
			is_staff=True,
		)

	def _request(self, data=None, query_params=None, files=None, post=None):
		return SimpleNamespace(
			data=data or {},
			query_params=query_params or {},
			FILES=files or SimpleNamespace(getlist=lambda _key: []),
			POST=post or {},
			user=self.admin_user,
			META={},
		)

	@patch('documents.views.settings.DOCREPO_DUAL_WRITE_LEGACY_ENABLED', False)
	@patch('documents.views.settings.DOCREPO_AUTO_ROUTE_UPLOAD_ENABLED', True)
	@patch('documents.views.record_audit_event')
	@patch('documents.views._find_active_duplicate_by_hash_size')
	@patch('documents.views.build_auto_storage_prefix')
	@patch('documents.views.infer_upload_metadata')
	@patch('documents.views.extract_text_from_pdf_bytes')
	def test_files_classify_preview_returns_ready_item(
		self,
		mock_extract_text_from_bytes,
		mock_infer_upload_metadata,
		mock_build_auto_storage_prefix,
		mock_find_duplicate,
		mock_record_audit,
	):
		fake_upload = SimpleNamespace(
			name='SCTR PENSION 02012026 FACILITIES.pdf',
			read=lambda: b'%PDF-1.4 classify-preview content',
		)
		files = SimpleNamespace(getlist=lambda _key: [fake_upload])

		mock_extract_text_from_bytes.return_value = ('SCTR PENSION FACILITIES', ['42177863'])
		mock_infer_upload_metadata.return_value = {
			'año': '2026',
			'razon_social': 'FACILITIES',
			'mes': '01',
			'banco': 'GENERAL',
			'tipo_documento': 'SCTR PENSION',
			'domain_code': 'SEGUROS',
		}
		mock_build_auto_storage_prefix.return_value = '2026/FACILITIES/01.ENERO/SEGUROS/SCTR PENSION'
		mock_find_duplicate.return_value = None

		request = self._request(files=files, post={})
		response = FilesClassifyPreviewView().post(request)

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.data['success'])
		self.assertEqual(response.data['summary']['total_files'], 1)
		self.assertEqual(response.data['summary']['ready'], 1)
		self.assertEqual(response.data['summary']['requires_confirmation'], 0)
		self.assertEqual(response.data['summary']['duplicates'], 0)
		self.assertEqual(response.data['files'][0]['status'], 'READY')
		self.assertEqual(response.data['files'][0]['domain'], 'SEGUROS')
		self.assertEqual(
			response.data['files'][0]['logical_path'],
			'2026/FACILITIES/01.ENERO/SEGUROS/SCTR PENSION/SCTR PENSION 02012026 FACILITIES.pdf'
		)

		mock_find_duplicate.assert_called_once()
		mock_record_audit.assert_called_once()

	@patch('documents.views.settings.DOCREPO_DUAL_WRITE_LEGACY_ENABLED', False)
	@patch('documents.views.settings.DOCREPO_AUTO_ROUTE_UPLOAD_ENABLED', True)
	@patch('documents.views.record_audit_event')
	@patch('documents.views._find_active_duplicate_by_hash_size')
	@patch('documents.views.build_auto_storage_prefix')
	@patch('documents.views.infer_upload_metadata')
	@patch('documents.views.extract_text_from_pdf_bytes')
	def test_files_classify_preview_marks_duplicate(
		self,
		mock_extract_text_from_bytes,
		mock_infer_upload_metadata,
		mock_build_auto_storage_prefix,
		mock_find_duplicate,
		mock_record_audit,
	):
		fake_upload = SimpleNamespace(
			name='FIN DE MES DESTACADOS_27022024.pdf',
			read=lambda: b'%PDF-1.4 classify-preview duplicate',
		)
		files = SimpleNamespace(getlist=lambda _key: [fake_upload])

		mock_extract_text_from_bytes.return_value = ('FIN DE MES DESTACADOS', ['42177863'])
		mock_infer_upload_metadata.return_value = {
			'año': '2024',
			'razon_social': 'RESGUARDO',
			'mes': '02',
			'banco': 'BCP',
			'tipo_documento': 'FIN DE MES DESTACADOS',
			'domain_code': 'CONSTANCIA_ABONO',
		}
		mock_build_auto_storage_prefix.return_value = '2024/RESGUARDO/02.FEBRERO/CONSTANCIA_ABONO/FIN DE MES DESTACADOS'
		mock_find_duplicate.return_value = SimpleNamespace(
			document=SimpleNamespace(id='dup-preview-id'),
			object_key='2024/RESGUARDO/02.FEBRERO/CONSTANCIA_ABONO/FIN DE MES DESTACADOS/FIN DE MES DESTACADOS_27022024.pdf',
		)

		request = self._request(files=files, post={})
		response = FilesClassifyPreviewView().post(request)

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.data['success'])
		self.assertEqual(response.data['summary']['total_files'], 1)
		self.assertEqual(response.data['summary']['ready'], 0)
		self.assertEqual(response.data['summary']['requires_confirmation'], 1)
		self.assertEqual(response.data['summary']['duplicates'], 1)
		self.assertEqual(response.data['files'][0]['status'], 'DUPLICATE')
		self.assertTrue(response.data['files'][0]['requires_confirmation'])
		self.assertEqual(response.data['files'][0]['duplicate']['document_id'], 'dup-preview-id')
		self.assertIn('duplicado_hash_size', response.data['files'][0]['warnings'])

		mock_find_duplicate.assert_called_once()
		mock_record_audit.assert_called_once()

	@patch('documents.views.settings.DOCREPO_DUAL_WRITE_LEGACY_ENABLED', False)
	@patch('documents.views.record_audit_event')
	@patch('documents.views.upsert_document_from_upload')
	@patch('documents.views.minio_client.put_object')
	@patch('documents.views._find_active_duplicate_by_hash_size')
	def test_files_upload_blocks_duplicate_by_hash_and_size(
		self,
		mock_find_duplicate,
		mock_put_object,
		mock_upsert,
		mock_record_audit,
	):
		fake_upload = SimpleNamespace(
			name='duplicado.pdf',
			read=lambda: b'%PDF-1.4 duplicate content',
		)
		files = SimpleNamespace(getlist=lambda _key: [fake_upload])

		mock_find_duplicate.return_value = SimpleNamespace(
			document=SimpleNamespace(id='dup-doc-id'),
			object_key='2026/FACILITIES/01.ENERO/SEGUROS/SCTR PENSION/duplicado.pdf',
		)

		request = self._request(files=files, post={})
		response = FilesUploadView().post(request)

		self.assertEqual(response.status_code, 400)
		self.assertFalse(response.data['success'])
		self.assertEqual(response.data['total_uploaded'], 0)
		self.assertEqual(response.data['total_errors'], 1)
		self.assertEqual(response.data['errors'][0]['code'], 'DUPLICATE_FILE')
		self.assertEqual(response.data['errors'][0]['existing_document_id'], 'dup-doc-id')

		mock_put_object.assert_not_called()
		mock_upsert.assert_not_called()
		mock_record_audit.assert_called_once()

	@patch('documents.views.settings.DOCREPO_DUAL_WRITE_LEGACY_ENABLED', False)
	@patch('documents.views.settings.DOCREPO_AUTO_ROUTE_UPLOAD_ENABLED', True)
	@patch('documents.views.record_audit_event')
	@patch('documents.views._find_active_duplicate_by_hash_size')
	@patch('documents.views.upsert_document_from_upload')
	@patch('documents.views.extract_text_from_pdf')
	@patch('documents.views.build_auto_storage_prefix')
	@patch('documents.views.infer_upload_metadata')
	@patch('documents.views.extract_text_from_pdf_bytes')
	@patch('documents.views.minio_client.stat_object')
	@patch('documents.views.minio_client.put_object')
	def test_files_upload_auto_routes_when_folder_missing(
		self,
		mock_put_object,
		mock_stat_object,
		mock_extract_text_from_bytes,
		mock_infer_upload_metadata,
		mock_build_auto_storage_prefix,
		mock_extract_text,
		mock_upsert,
		mock_find_duplicate,
		mock_record_audit,
	):
		fake_upload = SimpleNamespace(
			name='SCTR PENSION 02012026 FACILITIES.pdf',
			read=lambda: b'%PDF-1.4 auto-route test content',
		)
		files = SimpleNamespace(getlist=lambda _key: [fake_upload])

		mock_extract_text_from_bytes.return_value = ('SCTR PENSION FACILITIES', ['42177863'])
		mock_infer_upload_metadata.return_value = {
			'año': '2026',
			'razon_social': 'FACILITIES',
			'mes': '01',
			'banco': 'GENERAL',
			'tipo_documento': 'SCTR PENSION',
			'domain_code': 'SEGUROS',
		}
		mock_build_auto_storage_prefix.return_value = '2026/FACILITIES/01.ENERO/SEGUROS/SCTR PENSION'
		mock_find_duplicate.return_value = None

		mock_stat_object.return_value = SimpleNamespace(
			etag='"etag-auto"',
			last_modified=datetime.utcnow(),
		)
		mock_extract_text.return_value = ('contenido', ['42177863'])
		mock_upsert.return_value = SimpleNamespace(
			document=SimpleNamespace(id='doc-auto'),
			domain_code='SEGUROS',
		)

		request = self._request(files=files, post={})
		response = FilesUploadView().post(request)

		self.assertEqual(response.status_code, 201)
		self.assertTrue(response.data['success'])
		self.assertEqual(response.data['total_uploaded'], 1)
		self.assertEqual(
			response.data['uploaded'][0]['path'],
			'2026/FACILITIES/01.ENERO/SEGUROS/SCTR PENSION/SCTR PENSION 02012026 FACILITIES.pdf'
		)
		self.assertTrue(response.data['uploaded'][0]['auto_routed'])
		self.assertEqual(response.data['uploaded'][0]['domain_preview'], 'SEGUROS')

		mock_extract_text_from_bytes.assert_called_once()
		mock_find_duplicate.assert_called_once()
		mock_infer_upload_metadata.assert_called_once()
		mock_build_auto_storage_prefix.assert_called_once()
		mock_put_object.assert_called_once()
		mock_upsert.assert_called_once()
		mock_record_audit.assert_called_once()

	@patch('documents.views.settings.DOCREPO_DUAL_WRITE_LEGACY_ENABLED', False)
	@patch('documents.views.record_audit_event')
	@patch('documents.views._find_active_duplicate_by_hash_size')
	@patch('documents.views.upsert_document_from_upload')
	@patch('documents.views.extract_text_from_pdf')
	@patch('documents.views.extract_metadata')
	@patch('documents.views.minio_client.stat_object')
	@patch('documents.views.minio_client.put_object')
	def test_files_upload_ingests_docrepo_without_legacy_mirror(
		self,
		mock_put_object,
		mock_stat_object,
		mock_extract_metadata,
		mock_extract_text,
		mock_upsert,
		mock_find_duplicate,
		mock_record_audit,
	):
		fake_upload = SimpleNamespace(
			name='planilla_test.pdf',
			read=lambda: b'%PDF-1.4 test content',
		)
		files = SimpleNamespace(getlist=lambda _key: [fake_upload])

		mock_stat_object.return_value = SimpleNamespace(
			etag='"etag123"',
			last_modified=datetime.utcnow(),
		)
		mock_extract_metadata.return_value = {
			'año': '2025',
			'razon_social': 'RESGUARDO',
			'mes': '01',
			'banco': 'BCP',
			'tipo_documento': 'GENERAL',
		}
		mock_extract_text.return_value = ('contenido', ['12345678'])
		mock_upsert.return_value = SimpleNamespace(
			document=SimpleNamespace(id='doc-1'),
			domain_code='CONSTANCIA_ABONO',
		)
		mock_find_duplicate.return_value = None

		request = self._request(
			files=files,
			post={'folder': '2025/RESGUARDO'},
		)

		response = FilesUploadView().post(request)

		self.assertEqual(response.status_code, 201)
		self.assertTrue(response.data['success'])
		self.assertEqual(response.data['total_uploaded'], 1)
		self.assertEqual(response.data['total_errors'], 0)
		self.assertEqual(response.data['uploaded'][0]['path'], '2025/RESGUARDO/planilla_test.pdf')
		self.assertFalse(response.data['uploaded'][0]['legacy_sync_enabled'])

		mock_put_object.assert_called_once()
		mock_upsert.assert_called_once()
		mock_find_duplicate.assert_called_once()
		mock_record_audit.assert_called_once()

	@patch('documents.views.record_audit_event')
	@patch('documents.views.deactivate_document_by_storage_key')
	@patch('documents.views.PDFIndex.objects.filter')
	@patch('documents.views.minio_client.remove_object')
	def test_files_delete_deactivates_docrepo_and_returns_success(
		self,
		mock_remove_object,
		mock_legacy_filter,
		mock_deactivate,
		mock_record_audit,
	):
		mock_legacy_filter.return_value.delete.return_value = (2, {})
		mock_deactivate.return_value = SimpleNamespace(id='doc-2')

		request = self._request(data={'path': '2025/RESGUARDO/01.ENERO/BCP/delete_me.pdf'})
		response = FilesDeleteView().delete(request)

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.data['success'])
		self.assertEqual(response.data['legacy_deleted_count'], 2)
		self.assertEqual(response.data['docrepo_document_id'], 'doc-2')

		mock_remove_object.assert_called_once()
		mock_deactivate.assert_called_once()
		mock_record_audit.assert_called_once()

	@patch('documents.views.Document.objects.filter')
	def test_files_list_returns_paginated_docrepo_payload(self, mock_document_filter):
		record = SimpleNamespace(
			id='doc-list-1',
			domain_id='CONSTANCIA_ABONO',
			domain=SimpleNamespace(code='CONSTANCIA_ABONO'),
			company=SimpleNamespace(name='RESGUARDO'),
			period=SimpleNamespace(year=2025, month=1),
			storage_object=SimpleNamespace(
				object_key='2025/RESGUARDO/01.ENERO/BCP/archivo_listado.pdf',
				size_bytes=2048,
				last_modified=datetime(2026, 4, 20, 9, 0, 0),
			),
			index_state=SimpleNamespace(is_indexed=True),
			constancia_detail=SimpleNamespace(
				bank=SimpleNamespace(name='BCP'),
				payroll_type='CUADRO DE PERSONAL',
				legacy_tipo_documento='',
			),
			insurance_detail=None,
			tregistro_detail=None,
			indexed_at=datetime(2026, 4, 20, 9, 5, 0),
			source_path_legacy='',
		)

		queryset = MagicMock()
		queryset.select_related.return_value = queryset
		queryset.order_by.return_value = queryset
		queryset.count.return_value = 1
		queryset.__getitem__.return_value = [record]
		mock_document_filter.return_value = queryset

		request = self._request(
			query_params={
				'page': '1',
				'per_page': '50',
				'sort': 'indexed_at',
				'order': 'desc',
			}
		)
		response = FilesListView().get(request)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['total'], 1)
		self.assertEqual(len(response.data['files']), 1)
		self.assertEqual(response.data['files'][0]['path'], '2025/RESGUARDO/01.ENERO/BCP/archivo_listado.pdf')
		self.assertEqual(response.data['files'][0]['banco'], 'BCP')
		self.assertEqual(response.data['files'][0]['tipo_documento'], 'CUADRO DE PERSONAL')

	@patch('documents.views.Document.objects.filter')
	def test_folders_list_groups_paths_by_current_level(self, mock_document_filter):
		mock_document_filter.return_value.values_list.return_value = [
			'2025/RESGUARDO/01.ENERO/BCP/archivo_1.pdf',
			'2025/RESGUARDO/02.FEBRERO/BCP/archivo_2.pdf',
			'2025/TREGISTRO/01.ENERO/MOV/doc_3.pdf',
		]

		request = self._request(query_params={'parent': '2025/'})
		response = FoldersListView().get(request)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['current_path'], '2025/')
		self.assertEqual(len(response.data['folders']), 2)
		self.assertEqual(response.data['folders'][0]['name'], 'RESGUARDO')
		self.assertEqual(response.data['folders'][0]['count'], 2)
		self.assertEqual(response.data['folders'][1]['name'], 'TREGISTRO')
		self.assertEqual(response.data['folders'][1]['count'], 1)

	@patch('documents.views.Document.objects.filter')
	def test_bulk_search_returns_hits_and_missing_codes(self, mock_document_filter):
		record = SimpleNamespace(
			id='doc-bulk-1',
			domain=SimpleNamespace(code='CONSTANCIA_ABONO'),
			company=SimpleNamespace(name='RESGUARDO'),
			period=SimpleNamespace(year=2025, month=3),
			storage_object=SimpleNamespace(
				object_key='2025/RESGUARDO/03.MARZO/BCP/bulk_file.pdf',
				size_bytes=3072,
			),
			constancia_detail=SimpleNamespace(
				bank=SimpleNamespace(name='BCP'),
				payroll_type='CUADRO DE PERSONAL',
				legacy_tipo_documento='',
			),
			insurance_detail=None,
			tregistro_detail=None,
			employee_codes=SimpleNamespace(
				all=lambda: [SimpleNamespace(employee_code='12345678')]
			),
		)

		queryset = MagicMock()
		queryset.select_related.return_value = queryset
		queryset.prefetch_related.return_value = queryset
		queryset.distinct.return_value = queryset
		queryset.count.return_value = 1
		queryset.__iter__.return_value = iter([record])
		mock_document_filter.return_value = queryset

		request = self._request(data={'codigos': '12345678,99999999'})
		response = BulkSearchView().post(request)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['total'], 1)
		self.assertIn('12345678', response.data['codigos_encontrados'])
		self.assertIn('99999999', response.data['codigos_no_encontrados'])
		self.assertEqual(response.data['results'][0]['codigos_match'], ['12345678'])
