from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .throttling import LoginRateThrottle


class AuthLoginView(APIView):
    """Authenticate user and return JWT tokens plus user profile payload."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        username = str(request.data.get("username") or "").strip()
        password = request.data.get("password")

        if not username or not password:
            return Response(
                {"error": "Usuario y password son obligatorios."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(request=request, username=username, password=password)
        if user is None:
            return Response(
                {"error": "Credenciales invalidas."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            return Response(
                {"error": "El usuario esta inactivo."},
                status=status.HTTP_403_FORBIDDEN,
            )

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "role": "admin" if user.is_staff else "user",
                    "is_active": user.is_active,
                },
            },
            status=status.HTTP_200_OK,
        )


class AuthLogoutView(APIView):
    """Invalidate refresh token using blacklist support and close session."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = str(request.data.get("refresh") or "").strip()
        if not refresh_token:
            return Response(
                {"error": "El refresh token es obligatorio para cerrar sesion."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh_token)
            blacklist_method = getattr(token, "blacklist", None)
            if callable(blacklist_method):
                blacklist_method()
        except TokenError:
            return Response(
                {"error": "Refresh token invalido o expirado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"message": "Sesion cerrada correctamente."}, status=status.HTTP_200_OK)
