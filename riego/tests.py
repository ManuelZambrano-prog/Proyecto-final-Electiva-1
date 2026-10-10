import json
import re
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.contrib.sessions.models import Session
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.core.files.storage import default_storage
from django.utils import timezone
from datetime import timedelta
from io import BytesIO
from PIL import Image
from unittest.mock import Mock, patch

from .apps import clear_stale_sessions
from .models import Especie, HorarioDisponible, PerfilUsuario, Planta, SolicitudPlanta
from .mqtt import MQTTError, publish_plant_command


class RiegoFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='maria',
            email='maria@example.com',
            password='12345678'
        )
        self.admin_user = get_user_model().objects.create_user(
            username='admin',
            email='admin@example.com',
            password='12345678',
            is_staff=True,
            is_superuser=True,
        )
        self.especie = Especie.objects.create(nombre='Tomate')

    def csrf_token_from(self, response):
        match = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', response.content)
        self.assertIsNotNone(match, 'The response should contain a CSRF token field.')
        return match.group(1).decode()

    def test_user_can_register(self):
        response = self.client.post(
            reverse('register'),
            {'username': 'nuevo', 'email': 'nuevo@example.com', 'password1': 'Qwerty123', 'password2': 'Qwerty123'}
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(get_user_model().objects.filter(username='nuevo').exists())

    def test_login_does_not_show_registration_link(self):
        response = self.client.get(reverse('login'))
        self.assertNotContains(response, 'Registrarse')
        self.assertNotContains(response, 'Regístrate aquí')
        self.assertEqual(response.content.decode().count('Iniciar sesión'), 1)
        self.assertContains(response, '>Entrar</button>')

    def test_users_with_same_password_can_log_in_independently(self):
        shared_password = '1005814855'
        manuel = get_user_model().objects.create_user(
            username='manuel',
            password=shared_password,
        )
        self.admin_user.set_password(shared_password)
        self.admin_user.save(update_fields=['password'])
        host = 'localhost:8000'
        origin = 'http://localhost:8000'

        for username, expected_url in (
            ('manuel', reverse('panel')),
            ('admin', reverse('admin_dashboard')),
        ):
            client = Client(enforce_csrf_checks=True)
            response = client.get(reverse('login'), HTTP_HOST=host)
            csrf_token = self.csrf_token_from(response)
            response = client.post(
                reverse('login'),
                {
                    'username': username,
                    'password': shared_password,
                    'csrfmiddlewaretoken': csrf_token,
                },
                HTTP_HOST=host,
                HTTP_ORIGIN=origin,
                follow=True,
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.request['PATH_INFO'], expected_url)
            self.assertEqual(
                int(client.session['_auth_user_id']),
                manuel.pk if username == 'manuel' else self.admin_user.pk,
            )

    def test_registration_accepts_csrf_origin_on_port_8000(self):
        client = Client(enforce_csrf_checks=True)
        host = 'localhost:8000'
        response = client.get(reverse('register'), HTTP_HOST=host)
        self.assertIn(settings.CSRF_COOKIE_NAME, response.cookies)
        self.assertEqual(settings.CSRF_COOKIE_NAME, 'proyecto_riego_csrf_v2')
        client.cookies['csrftoken'] = 'obsolete-token-from-an-old-cookie'
        csrf_token = response.cookies[settings.CSRF_COOKIE_NAME].value
        response = client.post(
            reverse('register'),
            {
                'username': 'csrf-user',
                'email': 'csrf@example.com',
                'password1': 'Qwerty123',
                'password2': 'Qwerty123',
            },
            HTTP_HOST=host,
            HTTP_ORIGIN='http://localhost:8000',
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(response.status_code, 302)

    def test_admin_can_log_in_again_after_csrf_protected_logout(self):
        client = Client(enforce_csrf_checks=True)
        host = 'localhost:8000'
        origin = 'http://localhost:8000'
        login_endpoint = reverse('login')

        response = client.get(login_endpoint, HTTP_HOST=host)
        csrf_token = self.csrf_token_from(response)
        response = client.post(
            login_endpoint,
            {'username': 'admin', 'password': '12345678', 'csrfmiddlewaretoken': csrf_token},
            HTTP_HOST=host,
            HTTP_ORIGIN=origin,
        )
        self.assertEqual(response.status_code, 302)

        response = client.get(reverse('admin_dashboard'), HTTP_HOST=host)
        self.assertEqual(response.status_code, 200)
        csrf_token = self.csrf_token_from(response)
        session_key = client.session.session_key
        csrf_token_before_logout = csrf_token
        response = client.post(
            reverse('logout'),
            {'csrfmiddlewaretoken': csrf_token},
            HTTP_HOST=host,
            HTTP_ORIGIN=origin,
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Session.objects.filter(session_key=session_key).exists())
        self.assertEqual(
            response.cookies[settings.SESSION_COOKIE_NAME]['max-age'],
            0,
        )
        self.assertNotEqual(
            client.cookies[settings.CSRF_COOKIE_NAME].value,
            csrf_token_before_logout,
        )
        response = client.get(login_endpoint, HTTP_HOST=host)
        self.assertEqual(response.status_code, 200)
        csrf_token = self.csrf_token_from(response)
        response = client.post(
            login_endpoint,
            {'username': 'admin', 'password': '12345678', 'csrfmiddlewaretoken': csrf_token},
            HTTP_HOST=host,
            HTTP_ORIGIN=origin,
        )
        self.assertEqual(response.status_code, 302)

    def test_switching_from_user_to_admin_keeps_csrf_valid(self):
        client = Client(enforce_csrf_checks=True)
        host = 'localhost:8000'
        origin = 'http://localhost:8000'
        login_endpoint = reverse('login')

        response = client.get(login_endpoint, HTTP_HOST=host)
        csrf_token = client.cookies[settings.CSRF_COOKIE_NAME].value
        response = client.post(
            login_endpoint,
            {'username': 'maria', 'password': '12345678'},
            HTTP_HOST=host,
            HTTP_ORIGIN=origin,
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(response.status_code, 302)

        response = client.get(reverse('panel'), HTTP_HOST=host)
        self.assertEqual(response.status_code, 200)
        csrf_token = client.cookies[settings.CSRF_COOKIE_NAME].value
        response = client.post(
            reverse('logout'),
            {},
            HTTP_HOST=host,
            HTTP_ORIGIN=origin,
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(response.status_code, 302)

        response = client.get(login_endpoint, HTTP_HOST=host)
        self.assertEqual(response.status_code, 200)
        csrf_token = client.cookies[settings.CSRF_COOKIE_NAME].value
        response = client.post(
            login_endpoint,
            {'username': 'admin', 'password': '12345678'},
            HTTP_HOST=host,
            HTTP_ORIGIN=origin,
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(response.status_code, 302)
        response = client.get(reverse('admin_dashboard'), HTTP_HOST=host)
        self.assertEqual(response.status_code, 200)

    @patch('riego.views.publish_plant_command')
    def test_user_can_water_after_csrf_protected_login(self, publish_command):
        planta = Planta.objects.create(usuario=self.user, especie=self.especie, apodo='Sala')
        client = Client(enforce_csrf_checks=True)
        host = 'localhost:8000'
        origin = 'http://localhost:8000'
        login_endpoint = reverse('login')

        response = client.get(login_endpoint, HTTP_HOST=host)
        csrf_token = client.cookies[settings.CSRF_COOKIE_NAME].value
        response = client.post(
            login_endpoint,
            {'username': 'maria', 'password': '12345678'},
            HTTP_HOST=host,
            HTTP_ORIGIN=origin,
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(response.status_code, 302)

        response = client.get(reverse('panel'), HTTP_HOST=host)
        self.assertEqual(
            response.status_code,
            200,
            f'Unexpected panel response: {response.status_code}, {response.get("Location")}',
        )
        self.assertIn('no-store', response.headers['Cache-Control'])
        csrf_token = client.cookies[settings.CSRF_COOKIE_NAME].value
        response = client.post(
            reverse('toggle_riego', args=[planta.id]),
            {},
            HTTP_HOST=host,
            HTTP_ORIGIN=origin,
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 302)
        planta.refresh_from_db()
        self.assertTrue(planta.riego_activo)
        publish_command.assert_called_once_with(planta, True)

    def test_pages_with_post_forms_are_not_cached(self):
        response = self.client.get(reverse('login'))
        self.assertIn('no-store', response.headers['Cache-Control'])
        response = self.client.get(reverse('register'))
        self.assertIn('no-store', response.headers['Cache-Control'])

        self.client.login(username='admin', password='12345678')
        for url_name in ('admin_dashboard', 'admin_horarios', 'admin_crear_usuario', 'admin_agregar_planta'):
            response = self.client.get(reverse(url_name))
            self.assertIn('no-store', response.headers['Cache-Control'], url_name)

        self.client.logout()
        self.client.login(username='maria', password='12345678')
        for url_name in ('panel', 'nueva_planta'):
            response = self.client.get(reverse(url_name))
            self.assertIn('no-store', response.headers['Cache-Control'], url_name)

    def test_customer_sees_notice_when_no_schedule_is_available(self):
        self.client.login(username='maria', password='12345678')
        response = self.client.get(reverse('nueva_planta'))
        self.assertContains(response, 'El proveedor no ha publicado horarios disponibles.')
        self.assertContains(response, 'disabled>Enviar solicitud</button>')

    def test_customer_sees_notice_when_selected_day_has_no_schedule(self):
        HorarioDisponible.objects.create(fecha='2026-10-11', hora='08:00:00')
        HorarioDisponible.objects.create(fecha='2026-10-10', hora='09:00:00', disponible=False)
        self.client.login(username='maria', password='12345678')
        response = self.client.get(reverse('nueva_planta'))
        self.assertContains(response, '11/10/2026 - 08:00')
        self.assertNotContains(response, '10/10/2026 - 09:00')

    def test_admin_can_add_two_schedules_with_csrf_protection(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin_user)
        host = 'localhost:8000'
        endpoint = reverse('admin_horarios')

        for date in ('2026-10-10', '2026-10-11'):
            response = client.get(endpoint, HTTP_HOST=host)
            self.assertEqual(response.status_code, 200)
            csrf_token = client.cookies[settings.CSRF_COOKIE_NAME].value
            response = client.post(
                endpoint,
                {'fecha': date, 'hora': '08:00'},
                HTTP_HOST=host,
                HTTP_ORIGIN='http://localhost:8000',
                HTTP_X_CSRFTOKEN=csrf_token,
            )
            self.assertEqual(response.status_code, 302)

        self.assertEqual(HorarioDisponible.objects.count(), 2)

    def test_admin_can_toggle_schedule_availability(self):
        horario = HorarioDisponible.objects.create(fecha='2026-10-10', hora='08:00:00')
        self.client.login(username='admin', password='12345678')
        endpoint = reverse('admin_horarios')
        response = self.client.post(endpoint, {
            'accion': 'cambiar_disponibilidad',
            'horario_id': horario.id,
        })
        self.assertRedirects(response, endpoint)
        horario.refresh_from_db()
        self.assertFalse(horario.disponible)

        self.client.post(endpoint, {
            'accion': 'cambiar_disponibilidad',
            'horario_id': horario.id,
        })
        horario.refresh_from_db()
        self.assertTrue(horario.disponible)

    def test_admin_can_delete_unreserved_schedule(self):
        horario = HorarioDisponible.objects.create(fecha='2026-10-10', hora='08:00:00')
        self.client.login(username='admin', password='12345678')
        response = self.client.post(reverse('admin_horarios'), {
            'accion': 'eliminar',
            'horario_id': horario.id,
        })
        self.assertRedirects(response, reverse('admin_horarios'))
        self.assertFalse(HorarioDisponible.objects.filter(pk=horario.pk).exists())

    def test_admin_cannot_reopen_or_delete_reserved_schedule(self):
        horario = HorarioDisponible.objects.create(
            fecha='2026-10-10',
            hora='08:00:00',
            disponible=False,
        )
        SolicitudPlanta.objects.create(
            usuario=self.user,
            especie=self.especie,
            fecha_cita=horario.fecha,
            hora_cita=horario.hora,
            estado=SolicitudPlanta.Estado.PENDIENTE,
        )
        self.client.login(username='admin', password='12345678')
        endpoint = reverse('admin_horarios')
        self.client.post(endpoint, {
            'accion': 'cambiar_disponibilidad',
            'horario_id': horario.id,
        })
        self.client.post(endpoint, {
            'accion': 'eliminar',
            'horario_id': horario.id,
        })
        horario.refresh_from_db()
        self.assertFalse(horario.disponible)
        self.assertTrue(HorarioDisponible.objects.filter(pk=horario.pk).exists())

    def test_taken_schedule_becomes_unavailable_for_other_customers(self):
        horario = HorarioDisponible.objects.create(fecha='2026-10-10', hora='08:00:00')
        self.client.login(username='maria', password='12345678')
        response = self.client.post(reverse('nueva_planta'), {
            'especie': self.especie.id,
            'apodo': 'Ventana',
            'horario_disponible': horario.id,
        })
        self.assertRedirects(response, reverse('panel'))
        horario.refresh_from_db()
        self.assertFalse(horario.disponible)

        otro_usuario = get_user_model().objects.create_user(
            username='ana',
            email='ana@example.com',
            password='12345678',
        )
        self.client.logout()
        self.client.login(username=otro_usuario.username, password='12345678')
        response = self.client.post(reverse('nueva_planta'), {
            'especie': self.especie.id,
            'apodo': 'Otra planta',
            'horario_disponible': horario.id,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SolicitudPlanta.objects.count(), 1)
        self.assertFalse(HorarioDisponible.objects.get(pk=horario.pk).disponible)

    def test_user_panel_shows_plants(self):
        Planta.objects.create(usuario=self.user, especie=self.especie, apodo='Cocina', humedad_actual=50.5, temperatura_actual=24.1)
        self.client.login(username='maria', password='12345678')
        response = self.client.get(reverse('panel'))
        self.assertContains(response, 'Cocina')
        self.assertContains(response, '50.5')
        self.assertContains(response, '24.1')

    @override_settings(MEDIA_ROOT='/tmp/riego-test-media')
    def test_older_plant_shows_its_species_photo(self):
        image_bytes = BytesIO()
        Image.new('RGB', (2, 2), color='green').save(image_bytes, format='PNG')
        self.especie.foto.save(
            'tomate.png',
            SimpleUploadedFile('tomate.png', image_bytes.getvalue(), content_type='image/png'),
        )
        self.addCleanup(self.especie.foto.delete, save=False)
        planta = Planta.objects.create(usuario=self.user, especie=self.especie, apodo='Planta anterior')
        Planta.objects.filter(pk=planta.pk).update(fecha_agregada=timezone.now() - timedelta(days=365))

        self.client.login(username='maria', password='12345678')
        response = self.client.get(reverse('panel'))

        self.assertContains(response, 'class="plant-photo"')
        self.assertContains(response, 'width="148" height="148"')
        self.assertContains(response, 'src="/media/especies/tomate')

    def test_role_redirects_after_login(self):
        self.client.login(username='maria', password='12345678')
        response = self.client.get(reverse('home'))
        self.assertRedirects(response, reverse('panel'))

        self.client.login(username='admin', password='12345678')
        response = self.client.get(reverse('home'))
        self.assertRedirects(response, reverse('admin_dashboard'))

    def test_unauthenticated_user_is_redirected_to_login(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/cuentas/login/', response.url)

    def test_session_cleanup_removes_stale_sessions(self):
        from django.contrib.sessions.backends.db import SessionStore

        stale_session = SessionStore()
        stale_session['test'] = 'stale'
        stale_session.save()
        Session.objects.filter(session_key=stale_session.session_key).update(
            expire_date=timezone.now() - timedelta(seconds=1),
        )

        active_session = SessionStore()
        active_session['test'] = 'active'
        active_session.save()
        self.assertEqual(Session.objects.count(), 2)
        clear_stale_sessions()

        self.assertEqual(Session.objects.count(), 1)
        self.assertTrue(Session.objects.filter(session_key=active_session.session_key).exists())

    def test_admin_can_create_user_with_name_and_cedula(self):
        self.client.login(username='admin', password='12345678')
        response = self.client.post(
            reverse('admin_crear_usuario'),
            {
                'username': 'usuario1',
                'email': 'usuario1@example.com',
                'password1': 'Qwerty123',
                'password2': 'Qwerty123',
                'nombre': 'Ana Gomez',
                'cedula': '1234567890',
            },
        )
        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(username='usuario1')
        self.assertEqual(user.perfil.nombre, 'Ana Gomez')
        self.assertEqual(user.perfil.cedula, '1234567890')

    def test_created_user_can_login(self):
        get_user_model().objects.create_user(
            username='usuario1',
            email='usuario1@example.com',
            password='Qwerty123',
        )
        self.client.login(username='usuario1', password='Qwerty123')
        response = self.client.get(reverse('panel'))
        self.assertEqual(response.status_code, 200)

    def test_admin_and_users_follow_required_password_policy(self):
        self.admin_user.set_password('admin')
        self.admin_user.save()
        self.assertTrue(check_password('admin', self.admin_user.password))

        self.user.set_password('1234567890')
        self.user.save()
        self.assertTrue(check_password('1234567890', self.user.password))

        self.client.login(username='admin', password='admin')
        response = self.client.get(reverse('home'))
        self.assertRedirects(response, reverse('admin_dashboard'))

        self.client.logout()
        self.client.login(username='maria', password='1234567890')
        response = self.client.get(reverse('home'))
        self.assertRedirects(response, reverse('panel'))

    def test_admin_dashboard_lists_requests_and_slots(self):
        self.client.login(username='admin', password='12345678')
        HorarioDisponible.objects.create(fecha='2026-10-10', hora='08:00:00')
        SolicitudPlanta.objects.create(
            usuario=self.user,
            especie=self.especie,
            apodo='Huerto interior',
            fecha_cita='2026-10-10',
            hora_cita='08:00:00',
            estado='pendiente',
        )
        response = self.client.get(reverse('admin_dashboard'))
        self.assertContains(response, 'maria')
        self.assertContains(response, 'Huerto interior')
        self.assertContains(response, '2026-10-10')
        self.assertContains(response, 'Asignar planta al cliente')

    def test_admin_can_assign_requested_plant_directly_to_customer(self):
        solicitud = SolicitudPlanta.objects.create(
            usuario=self.user,
            especie=self.especie,
            apodo='Tomate de balcón',
            fecha_cita='2026-10-10',
            hora_cita='08:00:00',
        )
        self.client.login(username='admin', password='12345678')

        response = self.client.post(reverse('admin_dashboard'), {
            'accion': 'asignar_planta',
            'solicitud_id': solicitud.id,
        })

        self.assertRedirects(response, reverse('admin_dashboard'))
        planta = Planta.objects.get(usuario=self.user, especie=self.especie)
        self.assertEqual(planta.apodo, 'Tomate de balcón')
        self.assertEqual(planta.mqtt_id, 'MariaTomate1')
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, SolicitudPlanta.Estado.APROBADA)

        self.client.post(reverse('admin_dashboard'), {
            'accion': 'asignar_planta',
            'solicitud_id': solicitud.id,
        })
        self.assertEqual(Planta.objects.filter(usuario=self.user, especie=self.especie).count(), 1)

    def test_admin_can_assign_request_with_csrf_protection(self):
        solicitud = SolicitudPlanta.objects.create(
            usuario=self.user,
            especie=self.especie,
            apodo='Tomate protegido',
            fecha_cita='2026-10-10',
            hora_cita='08:00:00',
        )
        client = Client(enforce_csrf_checks=True)
        host = 'localhost:8000'
        login_endpoint = reverse('login')
        response = client.get(login_endpoint, HTTP_HOST=host)
        csrf_token = self.csrf_token_from(response)
        response = client.post(
            login_endpoint,
            {'username': 'admin', 'password': '12345678', 'csrfmiddlewaretoken': csrf_token},
            HTTP_HOST=host,
            HTTP_ORIGIN='http://localhost:8000',
        )
        self.assertEqual(response.status_code, 302)

        endpoint = reverse('admin_dashboard')
        response = client.get(endpoint, HTTP_HOST=host)
        self.assertEqual(response.status_code, 200)
        csrf_token = self.csrf_token_from(response)

        response = client.post(
            endpoint,
            {
                'accion': 'asignar_planta',
                'solicitud_id': solicitud.id,
                'csrfmiddlewaretoken': csrf_token,
            },
            HTTP_HOST=host,
            HTTP_ORIGIN='http://localhost:8000',
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Planta.objects.filter(usuario=self.user, especie=self.especie).exists())

    def test_plant_mqtt_ids_are_numbered_per_customer_and_species(self):
        especie = Especie.objects.create(nombre='Suculenta (Pachyphytum)')
        first = Planta.objects.create(usuario=self.user, especie=especie, apodo='Sala')
        second = Planta.objects.create(usuario=self.user, especie=especie, apodo='Ventana')
        otro_usuario = get_user_model().objects.create_user(
            username='manuelz',
            first_name='Manuel',
            email='manuel@example.com',
            password='12345678',
        )
        PerfilUsuario.objects.create(user=otro_usuario, nombre='Manuel Zambrano')
        third = Planta.objects.create(usuario=otro_usuario, especie=especie, apodo='Patio')

        self.assertEqual(first.mqtt_id, 'MariaSuculenta1')
        self.assertEqual(second.mqtt_id, 'MariaSuculenta2')
        self.assertEqual(third.mqtt_id, 'ManuelSuculenta1')

    def test_watering_publish_uses_readable_plant_mqtt_id(self):
        especie = Especie.objects.create(nombre='Suculenta')
        planta = Planta.objects.create(usuario=self.user, especie=especie)
        client = Mock()
        client.is_connected.return_value = True
        publish_result = Mock()
        publish_result.is_published.return_value = True
        client.publish.return_value = publish_result

        with patch('riego.mqtt.create_mqtt_client', return_value=client):
            publish_plant_command(planta, True)

        client.publish.assert_called_once_with(
            f'riego/plantas/{planta.mqtt_id}/comandos',
            json.dumps({'planta_id': planta.mqtt_id, 'regar': True}),
            qos=1,
        )

    def test_admin_can_assign_catalog_plant_to_customer(self):
        self.client.login(username='admin', password='12345678')
        response = self.client.post(reverse('admin_agregar_planta'), {
            'accion': 'asignar',
            'asignar-usuario': self.user.id,
            'asignar-especie': self.especie.id,
            'asignar-apodo': 'Ventana',
        })
        self.assertRedirects(response, reverse('admin_agregar_planta'))
        planta = Planta.objects.get(usuario=self.user, especie=self.especie)
        self.assertEqual(planta.apodo, 'Ventana')

    @override_settings(MEDIA_ROOT='/tmp/riego-test-media')
    def test_admin_can_add_catalog_species_with_photo(self):
        image_bytes = BytesIO()
        Image.new('RGB', (2, 2), color='green').save(image_bytes, format='PNG')
        self.client.login(username='admin', password='12345678')
        response = self.client.post(reverse('admin_agregar_planta'), {
            'accion': 'crear_especie',
            'especie-nombre': 'Albahaca',
            'especie-foto': SimpleUploadedFile('albahaca.png', image_bytes.getvalue(), content_type='image/png'),
        })
        self.assertRedirects(response, reverse('admin_agregar_planta'))
        especie = Especie.objects.get(nombre='Albahaca')
        self.assertTrue(default_storage.exists(especie.foto.name))
        self.addCleanup(especie.foto.delete, save=False)

    @override_settings(MEDIA_ROOT='/tmp/riego-test-media')
    def test_admin_can_add_photo_to_existing_species(self):
        image_bytes = BytesIO()
        Image.new('RGB', (2, 2), color='green').save(image_bytes, format='PNG')
        self.client.login(username='admin', password='12345678')
        response = self.client.post(reverse('admin_agregar_planta'), {
            'accion': 'actualizar_foto',
            'especie_id': self.especie.id,
            'foto': SimpleUploadedFile('tomate.png', image_bytes.getvalue(), content_type='image/png'),
        })
        self.assertRedirects(response, reverse('admin_agregar_planta'))
        self.especie.refresh_from_db()
        self.assertTrue(default_storage.exists(self.especie.foto.name))
        response = self.client.get(reverse('admin_agregar_planta'))
        self.assertContains(response, 'width="112" height="112"')
        self.addCleanup(self.especie.foto.delete, save=False)

    @override_settings(MEDIA_ROOT='/tmp/riego-test-media')
    def test_admin_can_delete_unused_catalog_species_and_photo(self):
        image_bytes = BytesIO()
        Image.new('RGB', (2, 2), color='green').save(image_bytes, format='PNG')
        self.especie.foto.save(
            'tomate.png',
            SimpleUploadedFile('tomate.png', image_bytes.getvalue(), content_type='image/png'),
        )
        foto_name = self.especie.foto.name
        self.client.login(username='admin', password='12345678')
        response = self.client.post(reverse('admin_agregar_planta'), {
            'accion': 'eliminar_especie',
            'especie_id': self.especie.id,
        })
        self.assertRedirects(response, reverse('admin_agregar_planta'))
        self.assertFalse(Especie.objects.filter(pk=self.especie.pk).exists())
        self.assertFalse(default_storage.exists(foto_name))

    def test_admin_cannot_delete_species_used_by_existing_plant(self):
        Planta.objects.create(usuario=self.user, especie=self.especie)
        self.client.login(username='admin', password='12345678')
        response = self.client.post(reverse('admin_agregar_planta'), {
            'accion': 'eliminar_especie',
            'especie_id': self.especie.id,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Especie.objects.filter(pk=self.especie.pk).exists())
        self.assertContains(response, 'tiene plantas o solicitudes asociadas')

    def test_admin_cannot_delete_species_with_pending_request(self):
        SolicitudPlanta.objects.create(
            usuario=self.user,
            especie=self.especie,
            fecha_cita='2026-10-10',
            hora_cita='08:00:00',
        )
        self.client.login(username='admin', password='12345678')
        response = self.client.post(reverse('admin_agregar_planta'), {
            'accion': 'eliminar_especie',
            'especie_id': self.especie.id,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Especie.objects.filter(pk=self.especie.pk).exists())
        self.assertContains(response, 'tiene plantas o solicitudes asociadas')

    @patch('riego.views.publish_plant_command')
    def test_watering_command_is_published_before_state_changes(self, publish_command):
        planta = Planta.objects.create(usuario=self.user, especie=self.especie)
        self.client.login(username='maria', password='12345678')
        response = self.client.post(reverse('toggle_riego', args=[planta.id]))
        planta.refresh_from_db()
        self.assertRedirects(response, reverse('panel'))
        self.assertTrue(planta.riego_activo)
        publish_command.assert_called_once_with(planta, True)

    @patch('riego.views.publish_plant_command')
    def test_watering_command_rejects_get_requests(self, publish_command):
        planta = Planta.objects.create(usuario=self.user, especie=self.especie)
        self.client.login(username='maria', password='12345678')
        response = self.client.get(reverse('toggle_riego', args=[planta.id]))
        self.assertEqual(response.status_code, 405)
        publish_command.assert_not_called()

    @patch('riego.views.publish_plant_command', side_effect=MQTTError('sin conexión'))
    def test_watering_state_is_unchanged_when_publish_fails(self, publish_command):
        planta = Planta.objects.create(usuario=self.user, especie=self.especie)
        self.client.login(username='maria', password='12345678')
        response = self.client.post(reverse('toggle_riego', args=[planta.id]), follow=True)
        planta.refresh_from_db()
        self.assertFalse(planta.riego_activo)
        self.assertContains(response, 'sin conexión')

    def test_sensor_telemetry_updates_plant_database_values(self):
        from .mqtt import update_plant_from_telemetry

        planta = Planta.objects.create(usuario=self.user, especie=self.especie)
        updated = update_plant_from_telemetry(
            f'riego/plantas/{planta.id}/sensores',
            {'temperatura': 23.5, 'humedad': 61},
        )
        planta.refresh_from_db()
        self.assertTrue(updated)
        self.assertEqual(planta.temperatura_actual, 23.5)
        self.assertEqual(planta.humedad_actual, 61)

    @override_settings(MQTT_SENSOR_TOPIC='garden/sensors/{plant_id}/reading')
    def test_sensor_telemetry_uses_configured_topic_pattern(self):
        from .mqtt import update_plant_from_telemetry

        planta = Planta.objects.create(usuario=self.user, especie=self.especie)
        updated = update_plant_from_telemetry(
            f'garden/sensors/{planta.id}/reading',
            {'temperature': 19, 'humidity': 44},
        )
        planta.refresh_from_db()
        self.assertTrue(updated)
        self.assertEqual(planta.temperatura_actual, 19)
        self.assertEqual(planta.humedad_actual, 44)

    def test_sensor_telemetry_can_address_plant_by_mqtt_id(self):
        from .mqtt import update_plant_from_telemetry

        planta = Planta.objects.create(usuario=self.user, especie=self.especie)
        self.assertTrue(update_plant_from_telemetry(
            f'riego/plantas/{planta.mqtt_id}/sensores',
            {'temperatura': 22, 'humedad': 58},
        ))
        planta.refresh_from_db()
        self.assertEqual(planta.temperatura_actual, 22)
        self.assertEqual(planta.humedad_actual, 58)


class PerfilFotoTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='maria',
            email='maria@example.com',
            password='12345678',
        )
        self.admin_user = get_user_model().objects.create_user(
            username='admin',
            email='admin@example.com',
            password='12345678',
            is_staff=True,
            is_superuser=True,
        )
        self.especie = Especie.objects.create(nombre='Tomate')

    def make_image(self, name='perfil.png'):
        image_bytes = BytesIO()
        Image.new('RGB', (4, 4), color='blue').save(image_bytes, format='PNG')
        return SimpleUploadedFile(name, image_bytes.getvalue(), content_type='image/png')

    @override_settings(MEDIA_ROOT='/tmp/riego-test-media')
    def test_user_can_upload_profile_photo(self):
        self.client.login(username='maria', password='12345678')
        response = self.client.post(reverse('mi_perfil'), {
            'nombre': 'Maria Lopez',
            'foto': self.make_image(),
        })
        self.assertRedirects(response, reverse('mi_perfil'))
        perfil = PerfilUsuario.objects.get(user=self.user)
        self.assertEqual(perfil.nombre, 'Maria Lopez')
        self.assertTrue(perfil.foto)
        self.assertTrue(default_storage.exists(perfil.foto.name))
        self.addCleanup(perfil.foto.delete, save=False)
        response = self.client.get(reverse('mi_perfil'))
        self.assertContains(response, 'class="plant-photo"')

    @override_settings(MEDIA_ROOT='/tmp/riego-test-media')
    def test_admin_dashboard_shows_user_photo_and_stats(self):
        perfil = PerfilUsuario.objects.create(
            user=self.user, nombre='Maria Lopez', cedula='123', plan='premium',
        )
        perfil.foto.save('maria.png', self.make_image('maria.png'))
        self.addCleanup(perfil.foto.delete, save=False)
        Planta.objects.create(usuario=self.user, especie=self.especie, apodo='Cocina')
        SolicitudPlanta.objects.create(
            usuario=self.user,
            especie=self.especie,
            fecha_cita='2026-10-10',
            hora_cita='08:00:00',
            estado=SolicitudPlanta.Estado.PENDIENTE,
        )
        self.client.login(username='admin', password='12345678')
        response = self.client.get(reverse('admin_dashboard'))
        self.assertContains(response, 'Maria Lopez')
        self.assertContains(response, 'Premium')
        self.assertContains(response, 'class="plant-photo user-photo"')
        info = {u.username: u for u in response.context['usuarios_info']}
        self.assertEqual(info['maria'].num_plantas, 1)
        self.assertEqual(info['maria'].num_pendientes, 1)

    def test_admin_can_create_user_with_plan(self):
        self.client.login(username='admin', password='12345678')
        response = self.client.post(reverse('admin_crear_usuario'), {
            'username': 'usuario1',
            'email': 'usuario1@example.com',
            'nombre': 'Ana Gomez',
            'cedula': '1234567890',
            'plan': 'estandar',
        })
        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(username='usuario1')
        self.assertEqual(user.perfil.plan, 'estandar')
