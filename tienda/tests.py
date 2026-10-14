from django.test import TestCase
from django.urls import reverse

from .models import KitRiego


class TiendaLandingTests(TestCase):
    def test_root_serves_storefront(self):
        response = self.client.get(reverse('index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Plataforma Web')

    def test_platform_button_points_to_platform_login(self):
        response = self.client.get(reverse('index'))
        self.assertContains(response, reverse('login'))

    def test_hero_trust_block_removed(self):
        response = self.client.get(reverse('index'))
        self.assertNotContains(response, '+450 Hogares y Apartamentos')
        self.assertNotContains(response, 'cero raíces ahogadas')

    def test_kits_have_one_valve_and_monthly_billing(self):
        response = self.client.get(reverse('index'))
        self.assertContains(response, 'Pago mensual')
        self.assertNotContains(response, 'Pago único')
        self.assertContains(response, '1 Electroválvulas')
        kits = {kit.slug: kit for kit in KitRiego.objects.all()}
        self.assertEqual(
            {slug: kits[slug].valvulas_incluidas for slug in kits},
            {slug: 1 for slug in kits},
        )
        self.assertEqual(
            {slug: int(kits[slug].precio) for slug in kits},
            {
                'kit-balcon-ventana': 99000,
                'kit-hogar-verde-pro': 169000,
                'kit-jardin-interior-smart': 259000,
            },
        )
