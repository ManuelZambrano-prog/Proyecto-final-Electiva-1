from datetime import timedelta
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class PerfilUsuario(models.Model):
    class Plan(models.TextChoices):
        BASICO = 'basico', 'Básico (1-3 plantas)'
        ESTANDAR = 'estandar', 'Estándar (4-8 plantas)'
        PREMIUM = 'premium', 'Premium (hasta 16 plantas)'

    class EstadoSuscripcion(models.TextChoices):
        ACTIVA = 'activa', 'Activa'
        CANCELADA = 'cancelada', 'Cancelada'
        PENDIENTE = 'pendiente_pago', 'Pendiente de pago'

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    nombre = models.CharField(max_length=120, blank=True)
    cedula = models.CharField(max_length=20, blank=True)
    plan = models.CharField(max_length=20, choices=Plan.choices, default=Plan.BASICO)
    foto = models.ImageField(upload_to='perfiles/', blank=True)
    estado_suscripcion = models.CharField(max_length=20, choices=EstadoSuscripcion.choices, default=EstadoSuscripcion.ACTIVA)
    fecha_proximo_pago = models.DateField(null=True, blank=True)

    @property
    def limite_plantas(self):
        limites = {
            self.Plan.BASICO: 3,
            self.Plan.ESTANDAR: 8,
            self.Plan.PREMIUM: 16,
        }
        return limites.get(self.plan, 3)

    @property
    def precio_plan(self):
        precios = {
            self.Plan.BASICO: 99000,
            self.Plan.ESTANDAR: 169000,
            self.Plan.PREMIUM: 279000,
        }
        return precios.get(self.plan, 99000)

    @property
    def esta_cancelada(self):
        return self.estado_suscripcion == self.EstadoSuscripcion.CANCELADA

    @property
    def total_plantas(self):
        return self.user.planta_set.count()

    @property
    def puede_agregar_planta(self):
        if self.esta_cancelada:
            return False
        return self.total_plantas < self.limite_plantas

    def save(self, *args, **kwargs):
        if not self.fecha_proximo_pago:
            self.fecha_proximo_pago = timezone.now().date() + timedelta(days=30)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nombre or self.user.username} - Plan {self.get_plan_display()} ({self.get_estado_suscripcion_display()})"


class PagoSuscripcion(models.Model):
    class Tipo(models.TextChoices):
        RENOVACION = 'renovacion', 'Renovación de Plan Actual'
        CAMBIO_PLAN = 'cambio_plan', 'Cambio de Plan'

    class Estado(models.TextChoices):
        PENDIENTE = 'pendiente', 'Pendiente de aprobación'
        APROBADO = 'aprobado', 'Aprobado'
        RECHAZADO = 'rechazado', 'Rechazado'

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pagos_suscripcion')
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.RENOVACION)
    plan_solicitado = models.CharField(max_length=20, choices=PerfilUsuario.Plan.choices)
    monto = models.DecimalField(max_digits=10, decimal_places=0)
    metodo_pago = models.CharField(max_length=60, default='Transferencia Bancaria / PSE')
    referencia_pago = models.CharField(max_length=120, blank=True, help_text="Código o referencia del comprobante")
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PENDIENTE)
    created_at = models.DateTimeField(auto_now_add=True)
    fecha_aprobacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.usuario.username} - {self.get_tipo_display()} ({self.plan_solicitado}) - {self.estado}"


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

    # --- NUEVOS CAMPOS ---
    umbral_humedad = models.FloatField(default=40.0, help_text="Umbral de humedad para activar riego automático")
    estado_servo = models.CharField(max_length=20, default='cerrado', help_text="Estado del servo: abierto/cerrado")
    ultima_lectura_mqtt = models.DateTimeField(null=True, blank=True)

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
    """Datos ambientales de telemetría asociados a cada cliente."""
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='datos_ambientales', null=True, blank=True)
    temperatura = models.FloatField(null=True, blank=True, default=None, help_text="Temperatura ambiente en °C")
    humedad_ambiente = models.FloatField(null=True, blank=True, default=None, help_text="Humedad ambiente en %")
    estado_valvula = models.CharField(max_length=20, default='cerrada', blank=True, help_text="Estado de la válvula general (abierta/cerrada)")
    fecha_actualizacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Datos Ambientales"
        verbose_name_plural = "Datos Ambientales"

    @classmethod
    def get_datos(cls, usuario=None):
        if usuario:
            obj, _ = cls.objects.get_or_create(usuario=usuario)
            return obj
        obj = cls.objects.filter(usuario__isnull=True).first()
        if not obj:
            obj = cls.objects.create(usuario=None)
        return obj

    def __str__(self):
        usuario_nom = self.usuario.username if self.usuario else "General"
        t = f"{self.temperatura}°C" if self.temperatura is not None else "--"
        h = f"{self.humedad_ambiente}%" if self.humedad_ambiente is not None else "--"
        v = f"Válvula: {self.estado_valvula}" if self.estado_valvula else ""
        return f"{usuario_nom}: {t} / {h} {v}".strip()
