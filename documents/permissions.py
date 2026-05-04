from rest_framework.permissions import BasePermission


ALL_DOCUMENT_DOMAINS = {"SEGUROS", "TREGISTRO", "CONSTANCIA_ABONO"}
SELECCION_DOCUMENT_DOMAINS = {"SEGUROS", "TREGISTRO"}


def user_in_group(user, group_name):
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return user.groups.filter(name__iexact=str(group_name).strip()).exists()


def can_manage_files(user):
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or user.is_staff:
        return True
    return user_in_group(user, "planillas")


def allowed_domains_for_user(user):
    if can_manage_files(user):
        return set(ALL_DOCUMENT_DOMAINS)
    if user_in_group(user, "seleccion"):
        return set(SELECCION_DOCUMENT_DOMAINS)
    return set()


class CanManageFiles(BasePermission):
    message = "No tiene permisos para gestionar archivos."

    def has_permission(self, request, view):
        return can_manage_files(request.user)
