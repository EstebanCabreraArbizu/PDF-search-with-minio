"""
Throttling Personalizado para Endpoints de Autenticación

🎓 LECCIÓN: ¿Por qué throttling específico para login?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
El endpoint de login (/api/token/) es el más atacado porque:
1. Permite intentos de fuerza bruta para adivinar contraseñas
2. No requiere autenticación previa (cualquiera puede intentar)
3. Un atacante puede probar miles de combinaciones usuario/contraseña

Solución: Limitar SEVERAMENTE cuántos intentos se permiten.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """
    Throttle específico para intentos de login.
    
    🎓 LECCIÓN: ¿Por qué heredamos de AnonRateThrottle?
    
    Porque cuando alguien intenta hacer login, AÚN NO está autenticado.
    Usamos AnonRateThrottle que identifica al usuario por su IP.
    
    Configuración:
    - scope = 'login' → busca en settings: DEFAULT_THROTTLE_RATES['login']
    - Valor recomendado: '5/minute' (5 intentos por minuto)
    """
    scope = 'login'


class SearchRateThrottle(UserRateThrottle):
    """
    Throttle específico para búsquedas.
    
    🎓 LECCIÓN: ¿Por qué heredamos de UserRateThrottle?
    
    Porque las búsquedas requieren estar autenticado (token JWT).
    UserRateThrottle identifica al usuario por su ID, no por IP.
    Esto significa que si un usuario inicia sesión desde varias IPs,
    todas comparten el mismo límite.
    
    Configuración:
    - scope = 'search' → busca en settings: DEFAULT_THROTTLE_RATES['search']
    - Valor recomendado: '60/minute' (60 búsquedas por minuto)
    """
    scope = 'search'


class BulkSearchRateThrottle(UserRateThrottle):
    """
    Throttle para búsquedas masivas (más restrictivo).
    
    🎓 LECCIÓN: Las búsquedas masivas son más pesadas para el servidor
    porque procesan múltiples códigos a la vez. Por eso un límite más bajo.
    """
    scope = 'bulk_search'
    # Si no se define 'bulk_search' en settings, usamos un rate por defecto
    # Podrías añadir en settings: 'bulk_search': '10/minute'


class MergeRateThrottle(UserRateThrottle):
    """Throttle para fusión de PDFs, una operación pesada de I/O y CPU."""
    scope = 'merge'
