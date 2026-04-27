import boto3
from django.conf import settings

def get_minio_client():
    return boto3.client(
        's3',
        endpoint_url=f"http://{settings.MINIO_ENDPOINT}",
        aws_access_key_id=settings.MINIO_ACCESS_KEY,
        aws_secret_access_key=settings.MINIO_SECRET_KEY,
    )

def download_pdf(object_name):
    client = get_minio_client()
    response = client.get_object(Bucket=settings.MINIO_BUCKET, Key=object_name)
    return response['Body'].read()