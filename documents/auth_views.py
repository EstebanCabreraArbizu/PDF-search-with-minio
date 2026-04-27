from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from auditlog.services import record_audit_event

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
            record_audit_event(
                action="AUTH_LOGIN_REJECTED",
                resource_type="auth_session",
                resource_id=username[:64],
                request=request,
                metadata={
                    "reason": "missing_credentials",
                    "status_code": status.HTTP_400_BAD_REQUEST,
                    "username": username,
                },
            )
            return Response(
                {"error": "Usuario y password son obligatorios."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(request=request, username=username, password=password)
        if user is None:
            record_audit_event(
                action="AUTH_LOGIN_FAILED",
                resource_type="auth_session",
                resource_id=username[:64],
                request=request,
                metadata={
                    "reason": "invalid_credentials",
                    "status_code": status.HTTP_401_UNAUTHORIZED,
                    "username": username,
                },
            )
            return Response(
                {"error": "Credenciales invalidas."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            record_audit_event(
                action="AUTH_LOGIN_DENIED",
                resource_type="auth_session",
                resource_id=str(user.id),
                request=request,
                actor=user,
                metadata={
                    "reason": "inactive_user",
                    "status_code": status.HTTP_403_FORBIDDEN,
                    "username": user.username,
                },
            )
            return Response(
                {"error": "El usuario esta inactivo."},
                status=status.HTTP_403_FORBIDDEN,
            )

        refresh = RefreshToken.for_user(user)
        user_role = "admin" if user.is_staff else "user"
        record_audit_event(
            action="AUTH_LOGIN_SUCCEEDED",
            resource_type="auth_session",
            resource_id=str(user.id),
            request=request,
            actor=user,
            metadata={
                "status_code": status.HTTP_200_OK,
                "username": user.username,
                "role": user_role,
            },
        )
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "role": user_role,
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
            record_audit_event(
                action="AUTH_LOGOUT_REJECTED",
                resource_type="auth_session",
                resource_id=str(getattr(request.user, "id", "") or "")[:64],
                request=request,
                metadata={
                    "reason": "missing_refresh_token",
                    "status_code": status.HTTP_400_BAD_REQUEST,
                },
            )
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
            record_audit_event(
                action="AUTH_LOGOUT_FAILED",
                resource_type="auth_session",
                resource_id=str(getattr(request.user, "id", "") or "")[:64],
                request=request,
                metadata={
                    "reason": "invalid_or_expired_refresh",
                    "status_code": status.HTTP_400_BAD_REQUEST,
                },
            )
            return Response(
                {"error": "Refresh token invalido o expirado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        record_audit_event(
            action="AUTH_LOGOUT_SUCCEEDED",
            resource_type="auth_session",
            resource_id=str(getattr(request.user, "id", "") or "")[:64],
            request=request,
            actor=request.user,
            metadata={
                "status_code": status.HTTP_200_OK,
            },
        )
        return Response({"message": "Sesion cerrada correctamente."}, status=status.HTTP_200_OK)
