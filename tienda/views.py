from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from .models import KitRiego, Pedido, ConsultaContacto, Testimonio
from .forms import PedidoForm, ConsultaContactoForm


def seed_data_if_empty():
    """Populate default kits and testimonials if database is new"""
    if KitRiego.objects.count() == 0:
        KitRiego.objects.create(
            nombre="Kit Balcón & Ventana",
            slug="kit-balcon-ventana",
            subtitulo="Perfecto para apartamentos pequeños y macetas de ventana (1 a 3 plantas).",
            precio=149000,
            precio_anterior=189000,
            plantas_recomendadas="1 - 3 plantas caseras",
            capacidad_tanque="Depósito compacto 4 Litros",
            valvulas_incluidas=3,
            manguera_metros=5,
            sensores_incluidos="1 Sensor Suelo Humedad + 1 Sensor Temp/Hum Ambiente",
            destacado=False,
            icono="🪴",
            orden=1,
            descripcion="El kit inicial perfecto para quien vive en apartamento y quiere mantener sus suculentas, pothos o aromáticas saludables sin preocuparse por regar manualmente cada día.",
            beneficios="3 electroválvulas independientes de bajo consumo\n5 metros de microtubo flexible negro anti-algas\nDepósito de 4L translúcido con tapa hermética\nSensor de humedad de suelo capacitivo (anti-óxido)\nSensor DHT de temperatura y humedad ambiente\nAcceso a la App Web con notificaciones en vivo\nMicrogoteros ajustables gota a gota (0 a 6 L/h)\nFácil instalación en 15 minutos sin herramientas"
        )
        KitRiego.objects.create(
            nombre="Kit Hogar Verde Pro",
            slug="kit-hogar-verde-pro",
            subtitulo="El sistema más completo para salas, balcones y jardines interiores (4 a 8 plantas).",
            precio=249000,
            precio_anterior=310000,
            plantas_recomendadas="4 - 8 plantas caseras",
            capacidad_tanque="Depósito mediano 10 Litros",
            valvulas_incluidas=8,
            manguera_metros=12,
            sensores_incluidos="3 Sensores Suelo Humedad + Sensor Temp/Hum Ambiente",
            destacado=True,
            icono="🌿",
            orden=2,
            descripcion="Nuestra solución estrella para amantes de las plantas de interior (Monsteras, Ficus, Helechos, Palmeras). Controla de manera independiente hasta 8 macetas y recibe alertas automáticas cuando la tierra esté reseca.",
            beneficios="8 electroválvulas solenoides con control independiente\n12 metros de microtubo capilar de silicona flexible\nTanque de agua de 10L con indicador de nivel flotante\n3 sensores de humedad de suelo para macetas clave\nSensor de precisión para temperatura y clima de la sala\nApp Web interactiva con registro de litros dosificados\nNotificaciones 'Tu planta necesita riego' con confirmación\nGoteros compensados por presión para riego uniforme\nAdaptador a corriente 12V 2A incluido + backup USB"
        )
        KitRiego.objects.create(
            nombre="Kit Jardín Interior Smart",
            slug="kit-jardin-interior-smart",
            subtitulo="Potencia y automatización total para colecciones grandes o terrazas (hasta 16 plantas).",
            precio=389000,
            precio_anterior=479000,
            plantas_recomendadas="Hasta 16 plantas",
            capacidad_tanque="Tanque 20L o conexión directa grifo",
            valvulas_incluidas=16,
            manguera_metros=25,
            sensores_incluidos="6 Sensores Suelo + Sensor Clima Completo",
            destacado=False,
            icono="🏡",
            orden=3,
            descripcion="El kit definitivo para terrazas, jardines verticales interiores o coleccionistas botánicos. Permite irrigar hasta 16 plantas con dosificación programable mililitro a mililitro.",
            beneficios="16 electroválvulas de alta durabilidad en bloque modular\n25 metros de manguera de distribución y derivaciones\nDepósito de 20 Litros o conexión con reductor a grifo\n6 sensores de humedad para distintas especies botánicas\nEstación de monitoreo de temperatura y humedad ambiental\nPanel de administración web avanzado con gráficas y horarios\nSistema anti-obstrucción con filtro de sedimentos en línea\nSoporte técnico prioritario y garantía extendida de 2 años"
        )

    if Testimonio.objects.count() == 0:
        Testimonio.objects.create(
            nombre="Carolina Mendoza",
            ubicacion="Medellín • Apartamento El Poblado",
            plantas="Monstera Deliciosa, Pothos y Ficus Lyrata",
            comentario="Estuve 3 semanas fuera por vacaciones y regresé encontrando mis plantas más verdes y hermosas que nunca. Poder ver en el celular la humedad y autorizar el riego con un toque es genial.",
            estrellas=5
        )
        Testimonio.objects.create(
            nombre="Andrés Felipe Gómez",
            ubicacion="Bogotá • Apartamento Cedritos",
            plantas="Suculentas, Helechos y Romero",
            comentario="En Bogotá el frío y la sequedad a veces engañan con la tierra. La alerta de que la humedad bajó al 25% y que la temperatura estaba en 18°C me evita ahogar las raíces. Sistema 10/10.",
            estrellas=5
        )
        Testimonio.objects.create(
            nombre="Valentina Ríos",
            ubicacion="Cali • Casa con jardín interior",
            plantas="Orquídeas, Calatheas y Anturios",
            comentario="Las electroválvulas son silenciosas y la manguera negra se esconde perfecto entre las macetas. La app web es súper intuitiva y el cálculo de litros me ayudó a no desperdiciar agua.",
            estrellas=5
        )


def index(request):
    seed_data_if_empty()
    kits = KitRiego.objects.all().order_by('orden')
    testimonios = Testimonio.objects.filter(activo=True)
    contacto_form = ConsultaContactoForm()

    if request.method == 'POST' and 'enviar_contacto' in request.POST:
        contacto_form = ConsultaContactoForm(request.POST)
        if contacto_form.is_valid():
            contacto_form.save()
            messages.success(request, '¡Gracias por contactarnos! Un especialista te responderá a la brevedad con la asesoría para tus plantas.')
            return redirect('index')

    return render(request, 'tienda/index.html', {
        'kits': kits,
        'testimonios': testimonios,
        'contacto_form': contacto_form,
    })


def detalle_kit(request, slug):
    kit = get_object_or_404(KitRiego, slug=slug)
    kits_relacionados = KitRiego.objects.exclude(id=kit.id)
    return render(request, 'tienda/detalle_kit.html', {
        'kit': kit,
        'kits_relacionados': kits_relacionados,
    })


def checkout(request):
    seed_data_if_empty()
    kit_slug = request.GET.get('kit')
    kit_inicial = None
    if kit_slug:
        kit_inicial = KitRiego.objects.filter(slug=kit_slug).first()

    if not kit_inicial:
        kit_inicial = KitRiego.objects.filter(destacado=True).first() or KitRiego.objects.first()

    if request.method == 'POST':
        form = PedidoForm(request.POST)
        if form.is_valid():
            pedido = form.save(commit=False)
            # Calcular total
            precio_base = pedido.kit.precio
            extra_tanque = 35000 if pedido.tanque_extra else 0
            extra_sensores = 28000 if pedido.sensores_extra else 0
            pedido.total = precio_base + extra_tanque + extra_sensores
            pedido.save()
            return redirect('confirmacion', codigo=pedido.codigo)
    else:
        form = PedidoForm(initial={
            'kit': kit_inicial,
            'plantas_en_casa': kit_inicial.valvulas_incluidas if kit_inicial else 4
        })

    kits = KitRiego.objects.all().order_by('orden')
    return render(request, 'tienda/checkout.html', {
        'form': form,
        'kits': kits,
        'kit_inicial': kit_inicial,
    })


def confirmacion(request, codigo):
    pedido = get_object_or_404(Pedido, codigo=codigo)
    return render(request, 'tienda/confirmacion.html', {
        'pedido': pedido
    })


def simulador(request):
    """Página dedicada para probar interactivamente cómo funciona la alerta y el riego inteligente"""
    return render(request, 'tienda/simulador.html')


def como_funciona(request):
    """Explicación detallada de la tecnología (válvulas, mangueras, sensores, app web)"""
    return render(request, 'tienda/como_funciona.html')
