# Usuario de prueba para testing

## Resumen

El proyecto incluye un comando de Django para crear usuarios de prueba de forma reproducible dentro del entorno Docker Compose. El flujo usa PostgreSQL del contenedor, evita scripts locales ad-hoc y prepara credenciales consistentes para las pruebas Playwright.

## Comando

```powershell
docker compose exec django-app python manage.py create_test_user `
  --username testadmin `
  --password "Test123456!" `
  --email testadmin@example.com `
  --full-name "Administrador de Prueba" `
  --admin
```

Si el usuario ya existe, el comando muestra una advertencia y termina sin modificarlo. Ese resultado es aceptable en validaciones repetibles.

## Credenciales de testing

| Usuario | Password | Rol | Uso |
| --- | --- | --- | --- |
| `testadmin` | `Test123456!` | Superusuario | Smoke tests y flujos administrativos |

Estas credenciales son solo para desarrollo/testing. No deben usarse en produccion.

## Validacion

```powershell
docker compose exec django-app python manage.py check
docker compose exec django-app python manage.py create_test_user --username testadmin --password "Test123456!" --email testadmin@example.com --full-name "Administrador de Prueba" --admin
docker compose exec django-app python manage.py shell -c "from documents.models import CustomUser; u=CustomUser.objects.get(username='testadmin'); print(f'{u.username}|staff={u.is_staff}|super={u.is_superuser}|active={u.is_active}')"
```

Resultado esperado:

```text
testadmin|staff=True|super=True|active=True
```

## Alcance

- No requiere migraciones.
- No agrega dependencias.
- No cambia permisos de usuarios existentes.
- Solo crea usuarios cuando no existen previamente.
