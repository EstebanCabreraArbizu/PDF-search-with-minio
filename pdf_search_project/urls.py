"""
URL configuration for pdf_search_project project.

🎓 LECCIÓN: ¿Por qué creamos una vista personalizada para /api/token/?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
La vista por defecto de SimpleJWT (TokenObtainPairView) NO tiene throttling.
Creamos ThrottledTokenObtainPairView que hereda de ella y añade nuestro
LoginRateThrottle para limitar intentos de login a 5/minuto.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from django.contrib import admin
from django.conf import settings
from django.urls import path, include
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from documents.throttling import LoginRateThrottle


class ThrottledTokenObtainPairView(TokenObtainPairView):
    """
    Vista de login con Rate Limiting aplicado.
    
    Hereda toda la funcionalidad de TokenObtainPairView
    pero añade LoginRateThrottle que limita a 5 intentos/minuto por IP.
    """
    throttle_classes = [LoginRateThrottle]


urlpatterns = [
    path(f'{settings.DJANGO_ADMIN_URL}/', admin.site.urls),
    path('api/v2/', include('docrepo.urls')),
    path('', include('documents.urls')),
    # 🔒 LOGIN con Rate Limiting (5 intentos/minuto)
    path('api/token/', ThrottledTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]

