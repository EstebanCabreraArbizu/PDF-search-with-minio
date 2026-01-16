from rest_framework import serializers
from .models import PDFIndex

class PDFIndexSerializer(serializers.ModelSerializer):
    class Meta:
        model = PDFIndex
        fields = '__all__'