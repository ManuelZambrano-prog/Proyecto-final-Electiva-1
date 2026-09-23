from django.contrib.auth.models import User
from django.db import models


class PerfilUsuario(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    nombre = models.CharField(max_length=120, blank=True)
    cedula = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"{self.nombre or self.user.username} - {self.cedula or 'Sin cédula'}"


class Especie(models.Model):
    nombre = models.CharField(max_length=100, help_text="Ej: Tomate, Lechuga")
    agua_por_riego_ml = models.IntegerField(help_text="Límite máximo de agua por riego en mililitros")

    def __str__(self):
        return self.nombre


class Planta(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    especie = models.ForeignKey(Especie, on_delete=models.SET_NULL, null=True, blank=True)
    apodo = models.CharField(max_length=100, blank=True, help_text="Ej: Tomates de la ventana")
    humedad_actual = models.FloatField(default=0.0)
    temperatura_actual = models.FloatField(default=0.0)
    riego_activo = models.BooleanField(default=False)
    fecha_agregada = models.DateTimeField(auto_now_add=True)

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