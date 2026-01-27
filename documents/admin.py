from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, PDFIndex, DownloadLog


# ═══════════════════════════════════════════════════════════════════════════
# CustomUser Admin - Extiende UserAdmin para mejor gestión de usuarios
# ═══════════════════════════════════════════════════════════════════════════
@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """Admin para usuarios personalizados con campos adicionales"""
    
    # Columnas visibles en la lista
    list_display = ('username', 'full_name', 'email', 'is_staff', 'is_active', 'date_joined')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'date_joined')
    search_fields = ('username', 'full_name', 'email')
    ordering = ('-date_joined',)
    
    # Añadir full_name a los fieldsets del formulario de edición
    fieldsets = UserAdmin.fieldsets + (
        ('Información Adicional', {'fields': ('full_name',)}),
    )
    
    # Añadir full_name al formulario de creación
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Información Adicional', {'fields': ('full_name',)}),
    )
    
    # Acciones personalizadas
    actions = ['reset_password_action', 'safe_delete_users']
    
    @admin.action(description='🔑 Resetear contraseña a "Liderman2026!"')
    def reset_password_action(self, request, queryset):
        """Resetea la contraseña de los usuarios seleccionados"""
        count = 0
        for user in queryset:
            user.set_password('Liderman2026!')
            user.save()
            count += 1
        self.message_user(request, f'✓ Se reseteó la contraseña de {count} usuario(s) a "Liderman2026!"')
    
    @admin.action(description='🗑️ Eliminar usuarios de forma segura (desvincula logs)')
    def safe_delete_users(self, request, queryset):
        """Elimina usuarios después de desvincular sus registros relacionados"""
        count = 0
        for user in queryset:
            # Desvincular DownloadLogs primero
            DownloadLog.objects.filter(user=user).update(user=None)
            
            # Intentar eliminar de otras tablas legacy (si existen)
            from django.db import connection
            with connection.cursor() as cursor:
                try:
                    # Tabla legacy de Flask
                    cursor.execute("UPDATE download_logs SET user_id = NULL WHERE user_id = %s", [user.id])
                except Exception:
                    pass  # La tabla puede no existir
            
            # Ahora eliminar el usuario
            user.delete()
            count += 1
        self.message_user(request, f'✓ Se eliminaron {count} usuario(s) de forma segura')


# ═══════════════════════════════════════════════════════════════════════════
# PDFIndex Admin - Vista mejorada del índice de PDFs
# ═══════════════════════════════════════════════════════════════════════════
@admin.register(PDFIndex)
class PDFIndexAdmin(admin.ModelAdmin):
    """Admin para el índice de PDFs con columnas descriptivas"""
    
    list_display = (
        'id',
        'archivo_nombre',
        'razon_social', 
        'banco', 
        'año', 
        'mes',
        'tipo_documento',
        'tamaño_kb',
        'is_indexed',
        'indexed_at'
    )
    
    list_filter = ('is_indexed', 'año', 'banco', 'razon_social')
    search_fields = ('minio_object_name', 'razon_social', 'banco', 'codigos_empleado')
    ordering = ('-indexed_at',)
    readonly_fields = ('indexed_at', 'last_modified', 'md5_hash')
    
    # Personalizar nombres de columnas
    @admin.display(description='Archivo')
    def archivo_nombre(self, obj):
        """Muestra solo el nombre del archivo, no la ruta completa"""
        if obj.minio_object_name:
            return obj.minio_object_name.split('/')[-1][:50]
        return '-'
    
    @admin.display(description='Tamaño (KB)')
    def tamaño_kb(self, obj):
        """Muestra el tamaño en KB formateado"""
        if obj.size_bytes:
            return f"{obj.size_bytes / 1024:.1f}"
        return '0'
    
    # Fieldsets organizados
    fieldsets = (
        ('Información del Archivo', {
            'fields': ('minio_object_name', 'tipo_documento', 'size_bytes', 'md5_hash')
        }),
        ('Metadatos', {
            'fields': ('razon_social', 'banco', 'año', 'mes')
        }),
        ('Indexación', {
            'fields': ('is_indexed', 'codigos_empleado', 'indexed_at', 'last_modified')
        }),
    )


# ═══════════════════════════════════════════════════════════════════════════
# DownloadLog Admin - Registro de descargas con columnas claras
# ═══════════════════════════════════════════════════════════════════════════
@admin.register(DownloadLog)
class DownloadLogAdmin(admin.ModelAdmin):
    """Admin para logs de descargas con columnas descriptivas"""
    
    list_display = (
        'id',
        'archivo_descargado',
        'usuario',
        'downloaded_at',
        'ip_address'
    )
    
    list_filter = ('downloaded_at', 'user')
    search_fields = ('filename', 'user__username', 'user__full_name', 'ip_address')
    ordering = ('-downloaded_at',)
    readonly_fields = ('downloaded_at',)
    date_hierarchy = 'downloaded_at'
    
    @admin.display(description='Archivo Descargado')
    def archivo_descargado(self, obj):
        """Muestra nombre del archivo descargado (truncado)"""
        if obj.filename:
            nombre = obj.filename.split('/')[-1]
            return nombre[:60] + '...' if len(nombre) > 60 else nombre
        return '-'
    
    @admin.display(description='Usuario')
    def usuario(self, obj):
        """Muestra el usuario de forma segura"""
        if obj.user:
            return obj.user.full_name or obj.user.username
        return '(Usuario eliminado)'
    
    fieldsets = (
        ('Descarga', {
            'fields': ('filename', 'downloaded_at')
        }),
        ('Usuario', {
            'fields': ('user', 'ip_address')
        }),
    )


# Personalizar títulos del admin
admin.site.site_header = "Sistema de Planillas - Administración"
admin.site.site_title = "Admin Planillas"
admin.site.index_title = "Panel de Administración"