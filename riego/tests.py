from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.contrib.sessions.models import Session
from django.test import TestCase
from django.urls import reverse

from .apps import clear_stale_sessions
from .models import Especie, HorarioDisponible, Planta, SolicitudPlanta


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
        self.especie = Especie.objects.create(nombre='Tomate', agua_por_riego_ml=400)

    def test_user_can_register(self):
        response = self.client.post(
            reverse('register'),
            {'username': 'nuevo', 'email': 'nuevo@example.com', 'password1': 'Qwerty123', 'password2': 'Qwerty123'}
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(get_user_model().objects.filter(username='nuevo').exists())

    def test_user_panel_shows_plants(self):
        Planta.objects.create(usuario=self.user, especie=self.especie, apodo='Cocina', humedad_actual=50.5, temperatura_actual=24.1)
        self.client.login(username='maria', password='12345678')
        response = self.client.get(reverse('panel'))
        self.assertContains(response, 'Cocina')
        self.assertContains(response, '50.5')
        self.assertContains(response, '24.1')

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

        session = SessionStore()
        session['test'] = 'value'
        session.save()
        self.assertEqual(Session.objects.count(), 1)

        clear_stale_sessions()

        self.assertEqual(Session.objects.count(), 0)

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
