from minio import Minio
from pathlib import Path
from dotenv import load_dotenv
import os
from io import BytesIO

# Cargar .env como en app.py
env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(env_path)

ENDPOINT = os.getenv('MINIO_ENDPOINT', 'minio:9000')
ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY', 'admin')
SECRET_KEY = os.getenv('MINIO_SECRET_KEY', 'password')
BUCKET = os.getenv('MINIO_BUCKET_NAME', 'planillas-pdfs')

print('Using:', ENDPOINT, ACCESS_KEY[:4], 'bucket=', BUCKET)

c = Minio(ENDPOINT, access_key=ACCESS_KEY, secret_key=SECRET_KEY, secure=True)

try:
    exists = c.bucket_exists(BUCKET)
    print('bucket_exists ->', exists)
except Exception as e:
    print('bucket_exists error ->', e)

try:
    objs = []
    for o in c.list_objects(BUCKET, recursive=True):
        objs.append(o.object_name)
        if len(objs) >= 10:
            break
    print('list_objects sample ->', objs)
except Exception as e:
    print('list_objects error ->', e)

# Try stat a known path from logs (example with spaces)
sample = 'Planillas Prueba/CIR_ALT_TRA_20100901481_43120253_1912202511130.pdf'
try:
    st = c.stat_object(BUCKET, sample)
    print('stat_object -> size', st.size)
except Exception as e:
    print('stat_object error ->', e)

# Try put_object small test
try:
    data = BytesIO(b'Test upload')
    name = 'test_folder/test_upload_from_script.txt'
    c.put_object(BUCKET, name, data, length=data.getbuffer().nbytes, content_type='text/plain')
    print('put_object OK ->', name)
    # cleanup
    c.remove_object(BUCKET, name)
    print('removed test object')
except Exception as e:
    print('put_object error ->', e)

# Now try get_object on first few listed objects (simulate indexer behavior)
for idx, name in enumerate(objs[:5]):
    try:
        print(f"\nTrying get_object on {name}")
        resp = c.get_object(BUCKET, name)
        b = resp.read(8)
        resp.close()
        print('get_object OK, first bytes len=', len(b))
    except Exception as e:
        print('get_object error ->', e)
