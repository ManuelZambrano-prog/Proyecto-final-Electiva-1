from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from riego.models import PerfilUsuario, Planta, Especie
from datetime import timedelta
from django.utils import timezone


class Command(BaseCommand):
    help = 'Restaura todos los usuarios, perfiles, contraseñas y plantas del proyecto.'

    def handle(self, *args, **options):
        # 1. Admin
        admin, _ = User.objects.get_or_create(username='admin', defaults={'is_staff': True, 'is_superuser': True})
        admin.is_staff = True
        admin.is_superuser = True
        admin.set_password('1005814855')
        admin.save()
        self.stdout.write('[OK] Usuario admin restaurado (clave: 1005814855)')

        # 2. Usuarios clientes
        usuarios_data = [
            {'username': 'manuel', 'nombre': 'Manuel', 'cedula': '1005814855', 'email': 'mszambrano855@gmail.com', 'plan': 'basico'},
            {'username': 'juliana', 'nombre': 'juliana', 'cedula': '1005815773', 'email': 'juliana@correo.com', 'plan': 'basico'},
            {'username': 'david', 'nombre': 'david', 'cedula': '1110232804', 'email': 'david@correo.com', 'plan': 'basico'},
            {'username': 'greison', 'nombre': 'Greison', 'cedula': '123456789', 'email': 'greison@correo.com', 'plan': 'basico'},
            {'username': 'nuevo_usuario', 'nombre': 'Nuevo Usuario', 'cedula': '1234', 'email': 'nuevo@correo.com', 'plan': 'basico'},
        ]

        usuarios_dict = {}
        for ud in usuarios_data:
            user, _ = User.objects.get_or_create(username=ud['username'], defaults={'email': ud['email']})
            user.set_password('1005814855')
            user.is_staff = False
            user.is_superuser = False
            user.save()

            perfil, _ = PerfilUsuario.objects.get_or_create(user=user)
            perfil.nombre = ud['nombre']
            perfil.cedula = ud['cedula']
            perfil.plan = ud['plan']
            perfil.estado_suscripcion = PerfilUsuario.EstadoSuscripcion.ACTIVA
            perfil.fecha_proximo_pago = timezone.now().date() + timedelta(days=30)
            perfil.save()
            usuarios_dict[ud['username']] = user
            self.stdout.write(f"[OK] Usuario {ud['username']} restaurado (clave: 1005814855)")

        # 3. Especies
        esp_cholla, _ = Especie.objects.get_or_create(
            nombre='Cactus Cholla (Cylindropuntia)',
            defaults={'nombre_cientifico': 'Cylindropuntia fulgida', 'umbral_riego': 40.0}
        )
        esp_suculenta, _ = Especie.objects.get_or_create(
            nombre='Suculenta (Pachyphytum)',
            defaults={'nombre_cientifico': 'Pachyphytum oviferum', 'umbral_riego': 40.0}
        )

        # 4. Plantas
        plantas_data = [
            {'mqtt_id': 'ManuelCactuscholla1', 'apodo': 'Cactus pequeño', 'user': 'manuel', 'especie': esp_cholla},
            {'mqtt_id': 'ManuelSuculenta1', 'apodo': 'Suculenta Pepita', 'user': 'manuel', 'especie': esp_suculenta},
            {'mqtt_id': 'JulianaSuculenta1', 'apodo': 'Copito', 'user': 'juliana', 'especie': esp_suculenta},
            {'mqtt_id': 'DavidCactuscholla1', 'apodo': 'Espinita', 'user': 'david', 'especie': esp_cholla},
            {'mqtt_id': 'DavidCactuscholla2', 'apodo': 'Cosia', 'user': 'david', 'especie': esp_cholla},
            {'mqtt_id': 'DavidSuculenta1', 'apodo': 'Celular', 'user': 'david', 'especie': esp_suculenta},
        ]

        for pd in plantas_data:
            user = usuarios_dict.get(pd['user'])
            if user:
                planta, _ = Planta.objects.get_or_create(
                    mqtt_id=pd['mqtt_id'],
                    defaults={
                        'usuario': user,
                        'apodo': pd['apodo'],
                        'especie': pd['especie'],
                        'umbral_humedad': 40.0,
                        'estado_servo': 'cerrado',
                        'riego_activo': False,
                    }
                )
                planta.usuario = user
                planta.apodo = pd['apodo']
                planta.especie = pd['especie']
                planta.save()
                self.stdout.write(f"[OK] Planta {pd['apodo']} ({pd['mqtt_id']}) vinculada a {pd['user']}")

        self.stdout.write(self.style.SUCCESS('Todos los usuarios, plantas y contraseñas han sido restaurados con éxito!'))
