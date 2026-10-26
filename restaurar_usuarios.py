import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.core.management import call_command

if __name__ == '__main__':
    print("Ejecutando restauracion completa de usuarios y plantas...")
    call_command('restaurar_datos')
