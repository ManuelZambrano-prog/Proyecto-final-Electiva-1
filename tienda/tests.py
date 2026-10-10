from django.test import TestCase
from django.urls import reverse


class TiendaLandingTests(TestCase):
    def test_root_serves_storefront(self):
        response = self.client.get(reverse('index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Plataforma Web')

    def test_platform_button_points_to_platform_login(self):
        response = self.client.get(reverse('index'))
        self.assertContains(response, reverse('login'))
