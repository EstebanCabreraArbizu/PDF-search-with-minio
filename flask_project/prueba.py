from minio import Minio
c = Minio("s3.liderman.net.pe", access_key="minioadmin", secret_key="wZ8pDqV2sX9m", secure=True)
print(c.bucket_exists("planillas-pdfs"))
print([o.object_name for o in c.list_objects("planillas-pdfs", recursive=True)])