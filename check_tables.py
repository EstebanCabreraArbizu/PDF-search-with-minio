import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pdf_search_project.settings')
django.setup()

tables = ['pdf_index', 'users', 'download_log']
with connection.cursor() as cursor:
    for table in tables:
        cursor.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s)", [table])
        exists = cursor.fetchone()[0]
        status = "✅ EXISTS" if exists else "❌ MISSING"
        print(f"{table}: {status}")
