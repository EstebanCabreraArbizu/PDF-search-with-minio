from rest_framework import serializers
from .models import PDFIndex

class PDFIndexSerializer(serializers.ModelSerializer):
    """
    Serializer compatible con el formato de Flask (to_dict).
    El frontend espera: filename, metadata{}, download_url, size_kb
    """
    filename = serializers.CharField(source='minio_object_name', read_only=True)
    metadata = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    size_kb = serializers.SerializerMethodField()
    indexed = serializers.BooleanField(source='is_indexed', read_only=True)
    
    class Meta:
        model = PDFIndex
        fields = ['id', 'filename', 'metadata', 'download_url', 'size_kb', 'indexed']
    
    def get_metadata(self, obj):
        """Retorna objeto metadata anidado como en Flask"""
        return {
            'razon_social': obj.razon_social or '',
            'banco': obj.banco or '',
            'mes': obj.mes or '',
            'año': obj.año or '',
            'tipo_documento': obj.tipo_documento or ''
        }
    
    def get_download_url(self, obj):
        return f'/api/download/{obj.minio_object_name}'
    
    def get_size_kb(self, obj):
        return round(obj.size_bytes / 1024, 2) if obj.size_bytes else 0