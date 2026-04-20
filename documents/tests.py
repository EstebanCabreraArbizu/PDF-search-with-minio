from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase


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
