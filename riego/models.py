from django.contrib.auth.models import User
from django.db import models
from django.utils.text import slugify


class PerfilUsuario(models.Model):
    class Plan(models.TextChoices):
        BASICO = 'basico', 'Básico'
        ESTANDAR = 'estandar', 'Estándar'
        PREMIUM = 'premium', 'Premium'

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    nombre = models.CharField(max_length=120, blank=True)
    cedula = models.CharField(max_length=20, blank=True)
    plan = models.CharField(max_length=20, choices=Plan.choices, blank=True)
    foto = models.ImageField(upload_to='perfiles/', blank=True)

    def __str__(self):
        return f"{self.nombre or self.user.username} - {self.cedula or 'Sin cédula'}"


class Especie(models.Model):
    nombre = models.CharField(max_length=100, help_text="Ej: Tomate, Lechuga")
    foto = models.ImageField(upload_to='especies/', blank=True)

    def __str__(self):
        return self.nombre


class Planta(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    especie = models.ForeignKey(Especie, on_delete=models.SET_NULL, null=True, blank=True)
    mqtt_id = models.CharField(max_length=180, unique=True, editable=False, null=True, blank=True)
    apodo = models.CharField(max_length=100, blank=True, help_text="Ej: Tomates de la ventana")
    humedad_actual = models.FloatField(default=0.0)
    temperatura_actual = models.FloatField(default=0.0)
    riego_activo = models.BooleanField(default=False)
    fecha_agregada = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Siempre generar mqtt_id si no existe
        if not self.mqtt_id and self.usuario_id:
            try:
                perfil = self.usuario.perfil
            except Exception:
                perfil = None
            nombre_visible = (perfil.nombre if perfil and perfil.nombre else self.usuario.first_name) or self.usuario.username or 'Usuario'
            nombre_usuario = slugify(nombre_visible.split()[0]).replace('-', '')[:80].capitalize() or 'Usuario'
            nombre_especie = self.especie.nombre.split('(')[0].strip() if self.especie_id else 'Planta'
            nombre_especie = slugify(nombre_especie).replace('-', '')[:80].capitalize() or 'Planta'
            base_id = f'{nombre_usuario}{nombre_especie}'
            numero = 1
            while type(self).objects.filter(mqtt_id=f'{base_id}{numero}').exclude(pk=self.pk).exists():
                numero += 1
            self.mqtt_id = f'{base_id}{numero}'
        
        # Asegurar que siempre se guarde
        super().save(*args, **kwargs)

    def __str__(self):
        nombre_mostrar = self.apodo if self.apodo else (self.especie.nombre if self.especie else "Planta sin especie")
        return f"{nombre_mostrar} - {self.usuario.username}"


class Electrovalvula(models.Model):
    numero_pin = models.IntegerField(unique=True)
    planta = models.OneToOneField(Planta, on_delete=models.SET_NULL, null=True, blank=True)
    esta_activa = models.BooleanField(default=False)

    def __str__(self):
        estado = "Abierta" if self.esta_activa else "Cerrada"
        return f"Válvula {self.numero_pin} ({estado})"


class HorarioDisponible(models.Model):
    fecha = models.DateField()
    hora = models.TimeField()
    disponible = models.BooleanField(default=True)

    class Meta:
        unique_together = (('fecha', 'hora'),)

    def __str__(self):
        estado = "Disponible" if self.disponible else "Ocupado"
        return f"{self.fecha} {self.hora} - {estado}"


class SolicitudPlanta(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = 'pendiente', 'Pendiente'
        APROBADA = 'aprobada', 'Aprobada'
        RECHAZADA = 'rechazada', 'Rechazada'

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='solicitudes_plantas')
    especie = models.ForeignKey(Especie, on_delete=models.PROTECT)
    apodo = models.CharField(max_length=100, blank=True, help_text="Nombre con el que quieres identificar la planta")
    fecha_cita = models.DateField()
    hora_cita = models.TimeField()
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PENDIENTE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        nombre = self.apodo if self.apodo else self.especie.nombre
        return f"{self.usuario.username} - {nombre} ({self.estado})"


class DatosAmbientales(models.Model):
    """Datos ambientales generales (singleton)"""
    temperatura = models.FloatField(default=0.0, help_text="Temperatura ambiente en °C")
    humedad_ambiente = models.FloatField(default=0.0, help_text="Humedad ambiente en %")
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Datos Ambientales"
        verbose_name_plural = "Datos Ambientales"

    def save(self, *args, **kwargs):
        self.pk = 1  # Fuerza singleton
        super().save(*args, **kwargs)

    @classmethod
    def get_datos(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return f"{self.temperatura}°C / {self.humedad_ambiente}%"
