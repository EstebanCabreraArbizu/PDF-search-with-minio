from types import SimpleNamespace
from datetime import datetime
from unittest import TestCase
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from documents.views import IndexStatsView, PopulateHashesView, ReindexView, SyncIndexView


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
