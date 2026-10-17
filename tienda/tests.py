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

    def test_simulator_removed(self):
        response = self.client.get(reverse('index'))
        self.assertNotContains(response, 'Mesa de Pruebas')
        self.assertNotContains(response, 'Simulador en Vivo')
        self.assertNotContains(response, 'sim-humidity')
        self.assertEqual(self.client.get('/simulador/').status_code, 404)

    def test_hardware_uses_photos_and_servos_without_tank(self):
        response = self.client.get(reverse('index'))
        content = response.content.decode()
        self.assertNotContains(response, 'Tanque de Almacenamiento')
        self.assertNotContains(response, 'capacidad_tanque')
        self.assertNotContains(response, 'Depósito de')
        self.assertContains(response, 'Servomotores')
        self.assertContains(response, 'Servomotores Uno por Planta')
        self.assertContains(response, 'Mangueras y Goteros Transparentes')
        for imagen in (
            'componentes/servos.jpg',
            'componentes/manguera.jpg',
            'componentes/sensor-humedad.jpg',
        ):
            self.assertContains(response, imagen)
        self.assertNotContains(response, 'class="component-icon">🔌')
        self.assertNotContains(response, 'class="component-icon">🚰')

    def test_checkout_with_servo_extra(self):
        from .models import KitRiego, Pedido

        self.client.get(reverse('index'))
        kit = KitRiego.objects.get(slug='kit-balcon-ventana')
        response = self.client.post(reverse('checkout'), {
            'kit': kit.pk,
            'nombre_completo': 'Ana Gomez',
            'email': 'ana@example.com',
            'telefono': '3001234567',
            'ciudad': 'Bogotá',
            'direccion': 'Calle 1 # 2-3',
            'plantas_en_casa': 2,
            'servo_extra': 'on',
            'metodo_pago': 'contraentrega',
        })
        self.assertEqual(response.status_code, 302)
        pedido = Pedido.objects.get()
        self.assertTrue(pedido.servo_extra)
        self.assertEqual(int(pedido.total), 99000 + 35000)

    def test_kits_have_one_servo_and_monthly_billing(self):
        response = self.client.get(reverse('index'))
        self.assertContains(response, 'Pago mensual')
        self.assertNotContains(response, 'Pago único')
        self.assertContains(response, '1 Servomotor')
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
