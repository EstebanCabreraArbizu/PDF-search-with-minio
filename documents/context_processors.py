from django.conf import settings

def debug_status(request):
    return {'DEBUG': settings.DEBUG}
