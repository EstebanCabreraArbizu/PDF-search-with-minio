"""
Middleware de Seguridad Personalizado

🎓 LECCIÓN: ¿Por qué necesitamos middleware personalizado?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Django incluye headers como X-Frame-Options y X-Content-Type-Options de forma
nativa, pero NO incluye:
- Referrer-Policy: Controla qué información del referrer se comparte
- Permissions-Policy: Deshabilita APIs del navegador que no necesitas

Este middleware añade esos headers a TODAS las respuestas.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


class SecurityHeadersMiddleware:
    """
    Middleware que añade headers de seguridad adicionales a cada respuesta.
    
    Headers añadidos:
    1. Referrer-Policy: Controla qué se envía en el header 'Referer'
    2. Permissions-Policy: Desactiva APIs del navegador potencialmente peligrosas
    """
    
    def __init__(self, get_response):
        """
        🎓 LECCIÓN: Django llama a __init__ UNA sola vez al iniciar el servidor.
        Aquí guardamos la referencia al siguiente middleware en la cadena.
        """
        self.get_response = get_response
    
    def __call__(self, request):
        """
        🎓 LECCIÓN: Django llama a __call__ en CADA petición HTTP.
        
        Flujo:
        1. La petición llega
        2. Llamamos al siguiente middleware/vista
        3. Obtenemos la respuesta
        4. Añadimos nuestros headers
        5. Devolvemos la respuesta modificada
        """
        # Obtener la respuesta del siguiente middleware/vista
        response = self.get_response(request)
        
        # ─────────────────────────────────────────────────────────────────────
        # REFERRER-POLICY
        # ─────────────────────────────────────────────────────────────────────
        # ¿Qué es el Referer?
        # Cuando navegas de página A a página B, el navegador envía a B
        # información sobre de dónde vienes (página A).
        # 
        # 'strict-origin-when-cross-origin' significa:
        # - Mismo sitio: Envía URL completa
        # - Otro sitio (HTTPS→HTTPS): Solo envía el dominio (ej: search.liderman.net.pe)
        # - Otro sitio (HTTPS→HTTP): No envía nada (protege contra downgrade)
        # ─────────────────────────────────────────────────────────────────────
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # ─────────────────────────────────────────────────────────────────────
        # PERMISSIONS-POLICY (antes Feature-Policy)
        # ─────────────────────────────────────────────────────────────────────
        # Deshabilita APIs del navegador que tu aplicación NO necesita.
        # ¿Por qué? Estas APIs pueden ser explotadas por atacantes:
        # 
        # - camera=(): No permitir acceso a cámara
        # - microphone=(): No permitir acceso a micrófono
        # - geolocation=(): No permitir acceso a ubicación
        # - payment=(): No permitir API de pagos del navegador
        # 
        # Si tu app NO usa estas funciones, deshabilitarlas reduce el riesgo.
        # ─────────────────────────────────────────────────────────────────────
        response['Permissions-Policy'] = (
            'accelerometer=(), '
            'ambient-light-sensor=(), '
            'autoplay=(), '
            'battery=(), '
            'camera=(), '
            'display-capture=(), '
            'document-domain=(), '
            'encrypted-media=(), '
            'fullscreen=(self), '
            'geolocation=(), '
            'gyroscope=(), '
            'layout-animations=(), '
            'magnetometer=(), '
            'microphone=(), '
            'midi=(), '
            'payment=(), '
            'picture-in-picture=(), '
            'speaker=(), '
            'usb=(), '
            'vibrate=(), '
            'vr=()'
        )
        
        return response
