from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120))
    role = db.Column(db.String(20), default='user')  # 'admin' o 'user'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    def set_password(self, password):
        """Hashea la contraseña antes de guardarla"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verifica si la contraseña es correcta"""
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'full_name': self.full_name,
            'role': self.role
        }

class DownloadLog(db.Model):
    """Auditoría: registra quién descarga qué"""
    __tablename__ = 'download_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    filename = db.Column(db.String(500), nullable=False)
    downloaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(50))
    
    user = db.relationship('User', backref='downloads')


class PDFIndex(db.Model):
    """
    Índice de PDFs almacenados en MinIO.
    Permite búsquedas rápidas sin listar todo el bucket cada vez.
    
    Beneficios:
    - Búsqueda en ~20ms vs ~2-5s (listando MinIO)
    - Full-text search en contenido del PDF
    - Filtros instantáneos por año, banco, mes, razón social
    """
    __tablename__ = 'pdf_index'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Identificador único del objeto en MinIO
    minio_object_name = db.Column(db.String(500), unique=True, nullable=False, index=True)
    
    # Metadata extraída de la ruta
    razon_social = db.Column(db.String(150), index=True)
    banco = db.Column(db.String(100), index=True)  # Aumentado para nombres largos
    mes = db.Column(db.String(2), index=True)  # "01" - "12"
    año = db.Column(db.String(4), index=True)  # "2024"
    tipo_documento = db.Column(db.String(300))  # Aumentado para nombres de archivo largos
    
    # Tamaño del archivo en bytes
    size_bytes = db.Column(db.BigInteger, default=0)
    
    # Hash MD5 del archivo (ETag de MinIO) - permite detectar archivos movidos
    md5_hash = db.Column(db.String(64), index=True)
    
    # Códigos de empleado encontrados (separados por coma para búsqueda rápida)
    # Se extraen durante indexación, permite búsqueda instantánea sin abrir PDFs
    codigos_empleado = db.Column(db.Text)  # "12345,67890,11111"
    
    # Timestamps
    indexed_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_modified = db.Column(db.DateTime)  # Fecha de modificación en MinIO
    
    # Estado del índice
    is_indexed = db.Column(db.Boolean, default=False)  # True cuando el contenido fue extraído
    index_error = db.Column(db.String(500))  # Mensaje de error si falló la indexación
    
    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.minio_object_name,
            'metadata': {
                'razon_social': self.razon_social,
                'banco': self.banco,
                'mes': self.mes,
                'año': self.año,
                'tipo_documento': self.tipo_documento
            },
            'download_url': f"/api/download/{self.minio_object_name}",
            'size_kb': round(self.size_bytes / 1024, 2) if self.size_bytes else 0,
            'indexed': self.is_indexed
        }
    
    def __repr__(self):
        return f'<PDFIndex {self.minio_object_name}>'