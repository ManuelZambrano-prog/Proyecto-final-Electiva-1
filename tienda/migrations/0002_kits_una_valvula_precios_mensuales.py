import re

from django.db import migrations


def actualizar_kits_una_valvula(apps, schema_editor):
    KitRiego = apps.get_model('tienda', 'KitRiego')
    datos = {
        'kit-balcon-ventana': 99000,
        'kit-hogar-verde-pro': 169000,
        'kit-jardin-interior-smart': 259000,
    }
    for slug, precio in datos.items():
        try:
            kit = KitRiego.objects.get(slug=slug)
        except KitRiego.DoesNotExist:
            continue
        kit.precio = precio
        kit.precio_anterior = None
        kit.valvulas_incluidas = 1
        if kit.beneficios:
            kit.beneficios = re.sub(
                r'^\d+ electroválvulas',
                '1 electroválvula',
                kit.beneficios,
                count=1,
            )
        kit.save(update_fields=['precio', 'precio_anterior', 'valvulas_incluidas', 'beneficios'])


class Migration(migrations.Migration):

    dependencies = [
        ('tienda', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(actualizar_kits_una_valvula, migrations.RunPython.noop),
    ]
