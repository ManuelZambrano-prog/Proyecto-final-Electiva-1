from datetime import date, time, timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from riego.models import (
    PerfilUsuario, Planta, Especie, SolicitudPlanta, HorarioDisponible, Electrovalvula
)


class Command(BaseCommand):
    help = 'Restaura todos los usuarios, perfiles, contraseñas, plantas y datos originales del proyecto.'

    def handle(self, *args, **options):
        self.stdout.write('Iniciando restauracion completa de datos...')

        # 1. Admin
        admin, _ = User.objects.get_or_create(username='admin', defaults={'email': 'admin@riego.com'})
        admin.email = 'admin@riego.com'
        admin.is_staff = True
        admin.is_superuser = True
        admin.set_password('1005814855')
        admin.save()
        self.stdout.write(self.style.SUCCESS('[OK] Usuario admin listo (clave: 1005814855)'))

        # 2. Usuarios clientes con sus cédulas como contraseñas oficiales
        usuarios_data = [
            {
                'username': 'manuel',
                'nombre': 'Manuel',
                'cedula': '1005814855',
                'email': 'mszambrano855@gmail.com',
                'foto': 'perfiles/WhatsApp_Image_2026-10-12_at_3.48.40_PM.jpeg',
                'plan': 'basico',
            },
            {
                'username': 'juliana',
                'nombre': 'juliana',
                'cedula': '1005815773',
                'email': 'juliana21cruz@gmail.com',
                'foto': '',
                'plan': 'basico',
            },
            {
                'username': 'david',
                'nombre': 'david',
                'cedula': '1110232804',
                'email': 'davidsr@gmail.com',
                'foto': '',
                'plan': 'basico',
            },
            {
                'username': 'greison',
                'nombre': 'Greison',
                'cedula': '123456789',
                'email': 'cualquiera@gmail.com',
                'foto': '',
                'plan': 'basico',
            },
            {
                'username': 'nuevo_usuario',
                'nombre': 'Nuevo Usuario',
                'cedula': '1234',
                'email': 'nuevo@correo.com',
                'foto': '',
                'plan': 'basico',
            },
        ]

        usuarios_dict = {'admin': admin}
        for ud in usuarios_data:
            user, _ = User.objects.get_or_create(username=ud['username'], defaults={'email': ud['email']})
            user.email = ud['email']
            user.is_staff = False
            user.is_superuser = False
            # La contraseña oficial es su cédula
            user.set_password(ud['cedula'])
            user.save()

            perfil, _ = PerfilUsuario.objects.get_or_create(user=user)
            perfil.nombre = ud['nombre']
            perfil.cedula = ud['cedula']
            perfil.plan = ud['plan']
            if ud['foto']:
                perfil.foto = ud['foto']
            perfil.estado_suscripcion = PerfilUsuario.EstadoSuscripcion.ACTIVA
            perfil.fecha_proximo_pago = timezone.now().date() + timedelta(days=30)
            perfil.save()
            usuarios_dict[ud['username']] = user
            self.stdout.write(
                f"[OK] Usuario '{ud['username']}' restaurado (clave/cedula: {ud['cedula']} o 1005814855)"
            )

        # 3. Especies del catálogo
        esp_cholla, _ = Especie.objects.get_or_create(
            nombre='Cactus Cholla (Cylindropuntia)',
            defaults={'foto': 'especies/Cactus_Cholla_Cylindropuntia.jpg'}
        )
        esp_cholla.foto = 'especies/Cactus_Cholla_Cylindropuntia.jpg'
        esp_cholla.save()

        esp_suculenta, _ = Especie.objects.get_or_create(
            nombre='Suculenta (Pachyphytum)',
            defaults={'foto': 'especies/suculenta.jpg'}
        )
        esp_suculenta.foto = 'especies/suculenta.jpg'
        esp_suculenta.save()

        esp_millonaria, _ = Especie.objects.get_or_create(
            nombre='Millonaria (Plectranthus verticillatus)',
            defaults={'foto': 'especies/millonaria.jpeg'}
        )
        esp_millonaria.foto = 'especies/millonaria.jpeg'
        esp_millonaria.save()

        especies_map = {
            'cholla': esp_cholla,
            'suculenta': esp_suculenta,
            'millonaria': esp_millonaria,
        }

        # 4. Plantas con sus dueños correspondientes
        plantas_data = [
            {'mqtt_id': 'ManuelCactuscholla1', 'apodo': 'Cactus pequeño', 'user': 'manuel', 'especie': esp_cholla, 'pin': 1},
            {'mqtt_id': 'ManuelSuculenta1', 'apodo': 'Suculenta Pepita', 'user': 'manuel', 'especie': esp_suculenta, 'pin': 2},
            {'mqtt_id': 'JulianaSuculenta1', 'apodo': 'Copito', 'user': 'juliana', 'especie': esp_suculenta, 'pin': 3},
            {'mqtt_id': 'DavidCactuscholla1', 'apodo': 'Espinita', 'user': 'david', 'especie': esp_cholla, 'pin': 4},
            {'mqtt_id': 'DavidCactuscholla2', 'apodo': 'Cosia', 'user': 'david', 'especie': esp_cholla, 'pin': 5},
            {'mqtt_id': 'DavidSuculenta1', 'apodo': 'Celular', 'user': 'david', 'especie': esp_suculenta, 'pin': 6},
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

                Electrovalvula.objects.update_or_create(
                    planta=planta,
                    defaults={'numero_pin': pd['pin'], 'esta_activa': False}
                )
                self.stdout.write(f"[OK] Planta '{pd['apodo']}' ({pd['mqtt_id']}) vinculada a '{pd['user']}'")

        # 5. Horarios de reserva
        horarios = [
            (date(2026, 9, 30), time(19, 30)),
            (date(2026, 9, 30), time(21, 30)),
            (date(2026, 10, 1), time(17, 0)),
            (date(2026, 10, 28), time(21, 50)),
            (date(2026, 10, 12), time(16, 35)),
        ]
        for f, h in horarios:
            HorarioDisponible.objects.get_or_create(fecha=f, hora=h, defaults={'disponible': False})

        # 6. Solicitudes históricas
        solicitudes = [
            {'apodo': 'Suculenta Pepita', 'fecha': date(2026, 9, 30), 'hora': time(19, 30), 'estado': 'aprobada', 'especie': esp_suculenta, 'user': 'manuel'},
            {'apodo': 'Copito', 'fecha': date(2026, 9, 30), 'hora': time(21, 30), 'estado': 'aprobada', 'especie': esp_suculenta, 'user': 'juliana'},
            {'apodo': 'Espinita', 'fecha': date(2026, 10, 1), 'hora': time(17, 0), 'estado': 'aprobada', 'especie': esp_cholla, 'user': 'david'},
            {'apodo': '', 'fecha': date(2026, 10, 28), 'hora': time(21, 50), 'estado': 'rechazada', 'especie': esp_suculenta, 'user': 'manuel'},
            {'apodo': 'Celular', 'fecha': date(2026, 10, 12), 'hora': time(16, 35), 'estado': 'aprobada', 'especie': esp_suculenta, 'user': 'david'},
        ]
        for s in solicitudes:
            user = usuarios_dict.get(s['user'])
            if user:
                SolicitudPlanta.objects.get_or_create(
                    usuario=user,
                    fecha_cita=s['fecha'],
                    hora_cita=s['hora'],
                    defaults={
                        'apodo': s['apodo'],
                        'estado': s['estado'],
                        'especie': s['especie'],
                    }
                )

        self.stdout.write(self.style.SUCCESS('\n[TODO COMPLETO] Todos los usuarios, plantas, perfiles y contraseñas han sido restaurados con éxito!'))
