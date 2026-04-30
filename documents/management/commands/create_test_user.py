"""
Comando para crear usuarios de prueba.
Uso: python manage.py create_test_user [--username USERNAME] [--password PASSWORD]
"""
from django.core.management.base import BaseCommand
from documents.models import CustomUser


class Command(BaseCommand):
    help = 'Crea un usuario de prueba para desarrollo/testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            default='testuser',
            help='Nombre de usuario (default: testuser)'
        )
        parser.add_argument(
            '--password',
            type=str,
            default='Test123456!',
            help='Contraseña (default: Test123456!)'
        )
        parser.add_argument(
            '--email',
            type=str,
            default='test@example.com',
            help='Email del usuario (default: test@example.com)'
        )
        parser.add_argument(
            '--full-name',
            type=str,
            default='Usuario de Prueba',
            help='Nombre completo (default: Usuario de Prueba)'
        )
        parser.add_argument(
            '--admin',
            action='store_true',
            help='Crear superusuario en lugar de usuario normal'
        )

    def handle(self, *args, **options):
        username = options['username']
        password = options['password']
        email = options['email']
        full_name = options['full_name']
        is_admin = options['admin']

        # Verificar si el usuario ya existe
        if CustomUser.objects.filter(username=username).exists():
            self.stdout.write(
                self.style.WARNING(
                    f'El usuario "{username}" ya existe. Elimínalo primero si quieres recrearlo.'
                )
            )
            return

        # Crear usuario
        if is_admin:
            CustomUser.objects.create_superuser(
                username=username,
                email=email,
                password=password,
                full_name=full_name
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f'Superusuario "{username}" creado exitosamente con privilegios de admin.'
                )
            )
        else:
            CustomUser.objects.create_user(
                username=username,
                email=email,
                password=password,
                full_name=full_name
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f'Usuario "{username}" creado exitosamente.'
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'  Username: {username}\n'
                f'  Password: {password}\n'
                f'  Email: {email}\n'
                f'  Full Name: {full_name}\n'
                f'  Admin: {"Sí" if is_admin else "No"}'
            )
        )
