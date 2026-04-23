import os, sys, json
os.chdir(r'C:\Proyecto - búsqueda inteligente con minio')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pdf_search_project.settings')
import django
django.setup()
from django.test import RequestFactory
from django.contrib.auth.models import User
from docrepo.views import SegurosV2SearchView

rf = RequestFactory()
payload = {'razon_social': 'Test', 'periodo': '2023-05'}
request = rf.post('/api/v2/seguros/search/', data=json.dumps(payload), content_type='application/json')
user = User.objects.first()
if not user:
    user = User.objects.create_user(username='test', password='test')
request.user = user
view = SegurosV2SearchView.as_view()
response = view(request)
print('Status:', response.status_code)
print('Content:', response.content[:500])
