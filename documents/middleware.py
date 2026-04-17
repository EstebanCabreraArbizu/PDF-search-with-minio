import logging
import re
import threading
import time

from django.conf import settings
from django.http import HttpResponseNotFound, JsonResponse


logger = logging.getLogger(__name__)


RATE_LIMITS = {
    'auth': {'requests': 5, 'window': 60, 'block_time': 1800},
    'upload': {'requests': 20, 'window': 60, 'block_time': 180},
    'api': {'requests': 200, 'window': 60, 'block_time': 60},
}


_RATE_STATE = {
    'hits': {},
    'blocked': {},
}
_RATE_LOCK = threading.Lock()


def get_client_ip(request):
    cf_ip = request.META.get('HTTP_CF_CONNECTING_IP')
    if cf_ip:
        return cf_ip.strip()

    real_ip = request.META.get('HTTP_X_REAL_IP')
    if real_ip:
        return real_ip.strip()

    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()

    return (request.META.get('REMOTE_ADDR') or '').strip()


def _admin_path_prefix():
    return f"/{settings.DJANGO_ADMIN_URL.strip('/')}/"


def _build_auth_patterns():
    return [
        '/api/token/',
        '/api/token/refresh/',
        _admin_path_prefix() + 'login/',
    ]


def _classify_scope(path):
    for auth_path in _build_auth_patterns():
        if path.startswith(auth_path):
            return 'auth'
    if path.startswith('/api/files/upload'):
        return 'upload'
    if path.startswith('/api/'):
        return 'api'
    return None


class IPRateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        scope = _classify_scope(request.path)
        if not scope:
            return self.get_response(request)

        ip = get_client_ip(request)
        if not ip:
            return self.get_response(request)

        now = int(time.time())
        cfg = RATE_LIMITS[scope]
        bucket = f'{scope}:{ip}'

        with _RATE_LOCK:
            blocked_until = _RATE_STATE['blocked'].get(bucket, 0)
            if blocked_until > now:
                retry_after = blocked_until - now
                return self._rate_limited_response(request, retry_after)

            data = _RATE_STATE['hits'].get(bucket)
            if not data or now - data['start'] >= cfg['window']:
                data = {'count': 0, 'start': now}

            data['count'] += 1
            _RATE_STATE['hits'][bucket] = data

            if data['count'] > cfg['requests']:
                blocked_until = now + cfg['block_time']
                _RATE_STATE['blocked'][bucket] = blocked_until
                retry_after = cfg['block_time']
                return self._rate_limited_response(request, retry_after)

        return self.get_response(request)

    def _rate_limited_response(self, request, retry_after):
        payload = {
            'error': {
                'code': 'rate_limited',
                'message': 'Demasiadas solicitudes. Intenta nuevamente más tarde.',
                'retry_after': retry_after,
            }
        }
        response = JsonResponse(payload, status=429)
        response['Retry-After'] = str(retry_after)
        return response


class AdminIPRestrictionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        admin_prefix = _admin_path_prefix()
        if not request.path.startswith(admin_prefix):
            return self.get_response(request)

        allowed_ips = getattr(settings, 'ADMIN_ALLOWED_IPS', [])
        if not allowed_ips:
            return self.get_response(request)

        client_ip = get_client_ip(request)
        if client_ip in allowed_ips:
            return self.get_response(request)

        logger.warning(
            'Admin access denied by IP restriction',
            extra={'path': request.path, 'ip': client_ip},
        )
        return HttpResponseNotFound('Not Found')


class RequestSanitizationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.patterns = [
            re.compile(r'<\s*script', re.IGNORECASE),
            re.compile(r'javascript\s*:', re.IGNORECASE),
            re.compile(r'\bunion\s+select\b', re.IGNORECASE),
            re.compile(r'\bor\s+1\s*=\s*1\b', re.IGNORECASE),
            re.compile(r'--'),
            re.compile(r';\s*drop\s+table', re.IGNORECASE),
        ]

    def __call__(self, request):
        if self._contains_suspicious_input(request):
            return JsonResponse(
                {
                    'error': {
                        'code': 'invalid_input',
                        'message': 'La solicitud contiene patrones no permitidos.',
                    }
                },
                status=400,
            )
        return self.get_response(request)

    def _contains_suspicious_input(self, request):
        values = []
        values.extend(request.GET.values())
        values.extend(request.POST.values())
        values.append(request.path)

        try:
            body = request.body.decode('utf-8', errors='ignore')
            if body:
                values.append(body)
        except Exception:
            pass

        for value in values:
            if not isinstance(value, str):
                continue
            for pattern in self.patterns:
                if pattern.search(value):
                    return True
        return False


class AuditLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.method not in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            return response

        if not (request.path.startswith('/api/') or request.path.startswith(_admin_path_prefix())):
            return response

        user = getattr(request, 'user', None)
        username = None
        if user and getattr(user, 'is_authenticated', False):
            username = user.get_username()

        logger.info(
            'audit_event',
            extra={
                'user': username or 'anonymous',
                'method': request.method,
                'path': request.path,
                'status_code': response.status_code,
                'ip': get_client_ip(request),
            },
        )
        return response


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response['Permissions-Policy'] = (
            'accelerometer=(), '
            'autoplay=(), '
            'camera=(), '
            'display-capture=(), '
            'encrypted-media=(), '
            'fullscreen=(self), '
            'geolocation=(), '
            'gyroscope=(), '
            'magnetometer=(), '
            'microphone=(), '
            'midi=(), '
            'payment=(), '
            'picture-in-picture=(), '
            'usb=(), '
            'xr-spatial-tracking=()'
        )
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'

        admin_prefix = _admin_path_prefix()
        is_admin_route = request.path.startswith(admin_prefix)
        response['Content-Security-Policy'] = self._build_csp(is_admin_route)

        return response

    def _build_csp(self, is_admin_route):
        script_src = "'self' https://static.cloudflareinsights.com"
        if is_admin_route:
            script_src = "'self' 'unsafe-inline' 'unsafe-eval' https://static.cloudflareinsights.com"

        directives = [
            "default-src 'self'",
            f"script-src {script_src}",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data:",
            "connect-src 'self'",
            "frame-src 'self'",
            "frame-ancestors 'self'",
            "base-uri 'self'",
            "form-action 'self'",
            "object-src 'none'",
        ]
        return '; '.join(directives)
