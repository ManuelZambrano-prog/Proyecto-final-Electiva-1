from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('riego', '0003_tanque_a_servos'),
    ]

    operations = [
        migrations.AddField(
            model_name='planta',
            name='umbral_humedad',
            field=models.FloatField(default=40.0),
        ),
        migrations.AddField(
            model_name='planta',
            name='estado_servo',
            field=models.CharField(default='cerrado', max_length=20),
        ),
        migrations.AddField(
            model_name='planta',
            name='ultima_lectura_mqtt',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
