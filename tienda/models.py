import uuid
from django.db import models


class KitRiego(models.Model):
    nombre = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    subtitulo = models.CharField(max_length=255)
    precio = models.DecimalField(max_digits=10, decimal_places=0, help_text="Precio en COP")
    precio_anterior = models.DecimalField(max_digits=10, decimal_places=0, blank=True, null=True)
    plantas_recomendadas = models.CharField(max_length=50, default="1 - 3 plantas")
    servo = models.CharField(max_length=50, default="Servomotor de precisión")
    valvulas_incluidas = models.PositiveIntegerField(default=3)
    manguera_metros = models.PositiveIntegerField(default=5)
    sensores_incluidos = models.CharField(max_length=150, default="1 Sensor Humedad Suelo + Temp/Hum Ambiente")
    destacado = models.BooleanField(default=False, help_text="Marcar como 'Más Popular'")
    descripcion = models.TextField()
    beneficios = models.TextField(help_text="Separar con salto de línea cada beneficio")
    icono = models.CharField(max_length=10, default="🌿")
    orden = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Kit de Riego"
        verbose_name_plural = "Kits de Riego"
        ordering = ['orden']

    def __str__(self):
        return f"{self.nombre} - ${self.precio:,.0f}"

    def lista_beneficios(self):
        return [b.strip() for b in self.beneficios.split('\n') if b.strip()]


class Pedido(models.Model):
    class MetodoPago(models.TextChoices):
        CONTRAENTREGA = 'contraentrega', 'Pago Contra Entrega en Domicilio'
        TRANSFERENCIA = 'transferencia', 'Transferencia Bancaria (Bancolombia, Nequi, Daviplata)'
        TARJETA = 'tarjeta', 'Tarjeta Débito / Crédito / PSE'

    class EstadoPedido(models.TextChoices):
        NUEVO = 'nuevo', 'Nuevo - Por Confirmar'
        EN_PREPARACION = 'preparacion', 'En Preparación'
        EN_CAMINO = 'en_camino', 'En Camino'
        ENTREGADO = 'entregado', 'Entregado'
        CANCELADO = 'cancelado', 'Cancelado'

    codigo = models.CharField(max_length=30, unique=True, editable=False)
    kit = models.ForeignKey(KitRiego, on_delete=models.PROTECT, related_name='pedidos')
    nombre_completo = models.CharField(max_length=150)
    email = models.EmailField()
    telefono = models.CharField(max_length=30)
    ciudad = models.CharField(max_length=100)
    direccion = models.CharField(max_length=200)
    barrio = models.CharField(max_length=100, blank=True)
    plantas_en_casa = models.PositiveIntegerField(default=3, help_text="¿Cuántas plantas tienes actualmente?")
    servo_extra = models.BooleanField(default=False, help_text="¿Desea servomotores adicionales para una dosificación más precisa?")
    sensores_extra = models.BooleanField(default=False, help_text="¿Desea sensores adicionales para cada maceta?")
    metodo_pago = models.CharField(max_length=20, choices=MetodoPago.choices, default=MetodoPago.CONTRAENTREGA)
    total = models.DecimalField(max_digits=12, decimal_places=0)
    estado = models.CharField(max_length=20, choices=EstadoPedido.choices, default=EstadoPedido.NUEVO)
    notas = models.TextField(blank=True, help_text="Comentarios o indicaciones para entrega")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pedido de Kit"
        verbose_name_plural = "Pedidos de Kits"
        ordering = ['-creado_en']

    def save(self, *args, **kwargs):
        if not self.codigo:
            unique_part = uuid.uuid4().hex[:6].upper()
            self.codigo = f"RIEGO-{unique_part}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.codigo} - {self.nombre_completo} ({self.kit.nombre})"


class ConsultaContacto(models.Model):
    TIPO_CHOICES = [
        ('duda_kit', 'Duda sobre qué kit elegir para mi casa'),
        ('compatibilidad', 'Compatibilidad con mis plantas específicas'),
        ('instalacion', 'Servicio de instalación o asesoría'),
        ('distribuidor', 'Compra por mayor / Proyecto especial'),
        ('otro', 'Otro asunto'),
    ]

    nombre = models.CharField(max_length=120)
    email = models.EmailField()
    telefono = models.CharField(max_length=30, blank=True)
    tipo_consulta = models.CharField(max_length=30, choices=TIPO_CHOICES, default='duda_kit')
    mensaje = models.TextField()
    creado_en = models.DateTimeField(auto_now_add=True)
    respondido = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Consulta de Contacto"
        verbose_name_plural = "Consultas de Contacto"
        ordering = ['-creado_en']

    def __str__(self):
        return f"{self.nombre} - {self.get_tipo_consulta_display()}"


class Testimonio(models.Model):
    nombre = models.CharField(max_length=100)
    ubicacion = models.CharField(max_length=100, help_text="Ej: Bogotá - Apartamento 8vo piso")
    plantas = models.CharField(max_length=120, help_text="Ej: Helecho de Boston, Monstera, Pothos")
    comentario = models.TextField()
    estrellas = models.PositiveSmallIntegerField(default=5)
    activo = models.BooleanField(default=True)
    fecha = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"{self.nombre} ({self.estrellas}★)"
