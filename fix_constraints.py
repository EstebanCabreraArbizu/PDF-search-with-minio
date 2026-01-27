import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pdf_search_project.settings')
django.setup()

def drop_not_null(table, column):
    with connection.cursor() as cursor:
        # Verificar si la columna existe antes de intentar modificarla
        cursor.execute("""
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_name=%s AND column_name=%s
        """, [table, column])
        
        if cursor.fetchone():
            print(f"   - Eliminando restricción NOT NULL de '{column}'...")
            try:
                cursor.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP NOT NULL;")
                print("     ✅ Hecho.")
            except Exception as e:
                print(f"     ⚠️ Error (quizás ya era nullable): {e}")
        else:
            print(f"   - La columna '{column}' no existe en '{table}', no es necesario hacer nada.")

with connection.cursor() as cursor:
    print("🔧 Reparando restricciones legacy en tabla 'users'...")
    
    # La columna 'password_hash' es del Flask antiguo y tiene NOT NULL.
    # Django usa 'password'. Al crear usuario, Django manda NULL a 'password_hash'.
    # Solución: Quitar el NOT NULL de password_hash.
    drop_not_null('users', 'password_hash')
    
    # También revisemos 'role' por si acaso, suele dar problemas similares
    drop_not_null('users', 'role')

    print("\n✅ Restricciones corregidas. Por favor intenta 'createsuperuser' nuevamente.")
