from datetime import timedelta
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_GET

from .forms import AsignarPlantaForm, EspecieForm, FotoEspecieForm, HorarioDisponibleForm, NuevaPlantaForm, RegistroForm, UsuarioAdminForm
from .models import DatosAmbientales, Electrovalvula, Especie, HorarioDisponible, PagoSuscripcion, PerfilUsuario, Planta, SolicitudPlanta
from .mqtt import MQTTError, publish_plant_command
from tienda.models import ConsultaContacto


@login_required
@never_cache
def home(request):
    if request.user.is_staff:
        return redirect('admin_dashboard')
    return redirect('panel')


@never_cache
def registro(request):
    if request.method == 'POST':
        form = RegistroForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, 'Registro completado correctamente.')
            return redirect('panel')
    else:
        form = RegistroForm()
    return render(request, 'riego/register.html', {'form': form})


@login_required
@never_cache
def panel_usuario(request):
    if request.user.is_staff:
        return redirect('admin_dashboard')
    plantas_usuario = Planta.objects.filter(usuario=request.user).select_related('especie').order_by('-fecha_agregada')
    solicitudes = SolicitudPlanta.objects.filter(usuario=request.user).select_related('especie').order_by('-created_at')
    datos_ambientales = DatosAmbientales.objects.filter(usuario=request.user).first()
    return render(request, 'riego/panel.html', {
        'plantas': plantas_usuario,
        'solicitudes': solicitudes,
        'datos_ambientales': datos_ambientales,
    })


@login_required
@never_cache
def nueva_planta(request):
    if request.user.is_staff:
        return redirect('admin_dashboard')
    
    perfil, _ = PerfilUsuario.objects.get_or_create(user=request.user)
    if perfil.esta_cancelada:
        messages.error(request, 'Tu suscripción se encuentra cancelada. Contactarse con el administrador para solucionar el problema.')
        return redirect('mi_plan')
    
    if not perfil.puede_agregar_planta:
        messages.warning(request, f'Has alcanzado el límite de {perfil.limite_plantas} plantas de tu plan {perfil.get_plan_display()}. Debes pasarte a un plan superior en la pestaña Plan para solicitar más plantas.')
        return redirect('mi_plan')

    if request.method == 'POST':
        form = NuevaPlantaForm(request.POST)
        if form.is_valid():
            horario_seleccionado = form.cleaned_data['horario_disponible']
            with transaction.atomic():
                slot_reservado = HorarioDisponible.objects.filter(
                    pk=horario_seleccionado.pk,
                    disponible=True,
                ).update(disponible=False)
                if slot_reservado:
                    solicitud = form.save(commit=False)
                    solicitud.usuario = request.user
                    solicitud.estado = SolicitudPlanta.Estado.PENDIENTE
                    solicitud.save()
                else:
                    form.add_error(None, 'Ese horario acaba de ser reservado. Elige otro horario disponible.')

            if slot_reservado:
                messages.success(request, 'Tu solicitud para agregar la planta fue enviada correctamente.')
                return redirect('panel')
    else:
        form = NuevaPlantaForm()

    hay_horarios_disponibles = form.fields['horario_disponible'].queryset.exists()
    return render(request, 'riego/nueva_planta.html', {
        'form': form,
        'hay_horarios_disponibles': hay_horarios_disponibles,
        'perfil': perfil,
    })


@login_required
@require_POST
def toggle_riego(request, planta_id):
    if request.user.is_staff:
        return redirect('admin_dashboard')
    
    perfil, _ = PerfilUsuario.objects.get_or_create(user=request.user)
    if perfil.esta_cancelada:
        messages.error(request, 'El servicio de riego está deshabilitado por suscripción cancelada. Contactarse con el administrador para solucionar el problema.')
        return redirect('panel')

    planta = get_object_or_404(Planta, pk=planta_id, usuario=request.user)
    esta_regando = (planta.estado_servo == 'abierto') or bool(planta.riego_activo)
    nuevo_estado = not esta_regando
    try:
        publish_plant_command(planta, nuevo_estado)
    except MQTTError as error:
        messages.error(request, f'No se pudo enviar la orden al controlador: {error}')
        return redirect('panel')

    planta.riego_activo = nuevo_estado
    planta.estado_servo = 'abierto' if nuevo_estado else 'cerrado'
    planta.save(update_fields=['riego_activo', 'estado_servo'])

    electrovalvula, created = Electrovalvula.objects.get_or_create(
        numero_pin=planta.id,
        defaults={'planta': planta, 'esta_activa': nuevo_estado}
    )
    electrovalvula.planta = planta
    electrovalvula.esta_activa = nuevo_estado
    electrovalvula.save()

    accion = 'iniciado' if nuevo_estado else 'detenido'
    messages.success(request, f'El riego de la planta fue {accion} correctamente.')
    return redirect('panel')


@staff_member_required
@never_cache
def admin_dashboard(request):
    usuarios = User.objects.filter(is_staff=False).order_by('username')
    solicitudes = SolicitudPlanta.objects.select_related('usuario', 'especie').order_by('-created_at')
    consultas = ConsultaContacto.objects.all().order_by('-creado_en')

    usuario_filtro = request.GET.get('usuario')
    if usuario_filtro:
        solicitudes = solicitudes.filter(usuario_id=usuario_filtro)

    if request.method == 'POST':
        accion = request.POST.get('accion', 'cambiar_estado')
        solicitud_id = request.POST.get('solicitud_id')
        if solicitud_id and accion == 'asignar_planta':
            solicitud = get_object_or_404(SolicitudPlanta, pk=solicitud_id)
            apodo = solicitud.apodo or solicitud.especie.nombre
            planta, creada = Planta.objects.get_or_create(
                usuario=solicitud.usuario,
                especie=solicitud.especie,
                apodo=apodo,
                defaults={
                    'humedad_actual': 0.0,
                    'temperatura_actual': 0.0,
                    'mqtt_id': '',
                },
            )
            # Forzar generación del mqtt_id si no existe
            if not planta.mqtt_id:
                planta.mqtt_id = ''
                planta.save()
            solicitud.estado = SolicitudPlanta.Estado.APROBADA
            solicitud.save()
            if creada:
                messages.success(request, f'{apodo} fue asignada a {solicitud.usuario.username}.')
            else:
                messages.info(request, f'{apodo} ya estaba asignada a {solicitud.usuario.username}.')
            return redirect('admin_dashboard')

        nueva_estado = request.POST.get('estado')
        if solicitud_id and nueva_estado:
            solicitud = get_object_or_404(SolicitudPlanta, pk=solicitud_id)
            solicitud.estado = nueva_estado
            solicitud.save()
            if nueva_estado == SolicitudPlanta.Estado.APROBADA:
                planta, creada = Planta.objects.get_or_create(
                    usuario=solicitud.usuario,
                    especie=solicitud.especie,
                    apodo=solicitud.apodo or solicitud.especie.nombre,
                    defaults={
                        'humedad_actual': 0.0,
                        'temperatura_actual': 0.0,
                        'mqtt_id': '',
                    },
                )
                if not planta.mqtt_id:
                    planta.mqtt_id = ''
                    planta.save()
                messages.success(request, f'Solicitud aprobada para {solicitud.usuario.username}.')
            elif nueva_estado == SolicitudPlanta.Estado.RECHAZADA:
                messages.warning(request, f'Solicitud rechazada para {solicitud.usuario.username}.')

            return redirect('admin_dashboard')

    usuarios_info = (
        User.objects.filter(is_staff=False)
        .select_related('perfil')
        .annotate(
            num_plantas=Count('planta', distinct=True),
            num_pendientes=Count(
                'solicitudes_plantas',
                filter=Q(solicitudes_plantas__estado=SolicitudPlanta.Estado.PENDIENTE),
                distinct=True,
            ),
        )
        .order_by('username')
    )

    pagos_pendientes = PagoSuscripcion.objects.filter(estado=PagoSuscripcion.Estado.PENDIENTE).select_related('usuario', 'usuario__perfil')

    return render(request, 'riego/admin_dashboard.html', {
        'usuarios': usuarios,
        'usuarios_info': usuarios_info,
        'solicitudes': solicitudes,
        'consultas': consultas,
        'pagos_pendientes': pagos_pendientes,
        'usuario_filtro': usuario_filtro,
        'total_usuarios': usuarios.count(),
        'solicitudes_pendientes': SolicitudPlanta.objects.filter(estado=SolicitudPlanta.Estado.PENDIENTE).count(),
        'pagos_pendientes_count': pagos_pendientes.count(),
        'horarios_disponibles': HorarioDisponible.objects.filter(disponible=True).count(),
        'consultas_count': consultas.count(),
    })


@staff_member_required
@never_cache
def admin_crear_usuario(request):
    if request.method == 'POST':
        form = UsuarioAdminForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'Usuario {user.username} creado correctamente.')
            return redirect('admin_dashboard')
    else:
        form = UsuarioAdminForm()
    return render(request, 'riego/admin_crear_usuario.html', {'form': form})


@staff_member_required
@never_cache
def admin_horarios(request):
    form = HorarioDisponibleForm()
    if request.method == 'POST':
        accion = request.POST.get('accion', 'guardar')
        if accion == 'cambiar_disponibilidad':
            horario = get_object_or_404(HorarioDisponible, pk=request.POST.get('horario_id'))
            nueva_disponibilidad = not horario.disponible
            tiene_reserva = SolicitudPlanta.objects.filter(
                fecha_cita=horario.fecha,
                hora_cita=horario.hora,
                estado__in=[SolicitudPlanta.Estado.PENDIENTE, SolicitudPlanta.Estado.APROBADA],
            ).exists()
            if nueva_disponibilidad and tiene_reserva:
                messages.error(request, 'No se puede habilitar un horario con una reserva pendiente o aprobada.')
            else:
                horario.disponible = nueva_disponibilidad
                horario.save(update_fields=['disponible'])
                messages.success(request, 'Disponibilidad del horario actualizada.')
            return redirect('admin_horarios')

        if accion == 'eliminar':
            horario = get_object_or_404(HorarioDisponible, pk=request.POST.get('horario_id'))
            tiene_reserva = SolicitudPlanta.objects.filter(
                fecha_cita=horario.fecha,
                hora_cita=horario.hora,
                estado__in=[SolicitudPlanta.Estado.PENDIENTE, SolicitudPlanta.Estado.APROBADA],
            ).exists()
            if tiene_reserva:
                messages.error(request, 'No se puede eliminar un horario con una reserva pendiente o aprobada.')
            else:
                horario.delete()
                messages.success(request, 'Horario eliminado correctamente.')
            return redirect('admin_horarios')

        form = HorarioDisponibleForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Horario disponible registrado correctamente.')
            return redirect('admin_horarios')

    horarios = HorarioDisponible.objects.order_by('fecha', 'hora')
    return render(request, 'riego/admin_horarios.html', {'form': form, 'horarios': horarios})


@staff_member_required
@never_cache
def admin_agregar_planta(request):
    asignar_form = AsignarPlantaForm(prefix='asignar')
    especie_form = EspecieForm(prefix='especie')
    foto_form = FotoEspecieForm()

    if request.method == 'POST':
        if request.POST.get('accion') == 'asignar':
            asignar_form = AsignarPlantaForm(request.POST, prefix='asignar')
            if asignar_form.is_valid():
                planta = asignar_form.save()
                messages.success(request, f'{planta} fue agregada correctamente.')
                return redirect('admin_agregar_planta')
        elif request.POST.get('accion') == 'crear_especie':
            especie_form = EspecieForm(request.POST, request.FILES, prefix='especie')
            if especie_form.is_valid():
                especie_form.save()
                messages.success(request, 'La especie y su foto fueron agregadas al catálogo.')
                return redirect('admin_agregar_planta')
        elif request.POST.get('accion') == 'actualizar_foto':
            foto_form = FotoEspecieForm(request.POST, request.FILES)
            especie = get_object_or_404(Especie, pk=request.POST.get('especie_id'))
            if foto_form.is_valid():
                especie.foto = foto_form.cleaned_data['foto']
                especie.save(update_fields=['foto'])
                messages.success(request, f'La foto de {especie.nombre} fue guardada.')
                return redirect('admin_agregar_planta')
        elif request.POST.get('accion') == 'eliminar_especie':
            especie = get_object_or_404(Especie, pk=request.POST.get('especie_id'))
            tiene_plantas = Planta.objects.filter(especie=especie).exists()
            tiene_solicitudes = SolicitudPlanta.objects.filter(especie=especie).exists()
            if tiene_plantas or tiene_solicitudes:
                messages.error(request, f'No se puede eliminar {especie.nombre}: tiene plantas o solicitudes asociadas.')
            else:
                foto = especie.foto
                nombre = especie.nombre
                especie.delete()
                if foto:
                    foto.delete(save=False)
                messages.success(request, f'{nombre} fue eliminada del catálogo.')
                return redirect('admin_agregar_planta')

    return render(request, 'riego/admin_agregar_planta.html', {
        'asignar_form': asignar_form,
        'especie_form': especie_form,
        'foto_form': foto_form,
        'especies': Especie.objects.order_by('nombre'),
    })


@login_required
@never_cache
@require_GET
def api_datos_plantas(request):
    """Devuelve JSON con estado de plantas y datos ambientales SOLO del usuario autenticado."""
    if request.user.is_staff:
        usuario_id = request.GET.get('usuario')
        if usuario_id:
            user_target = User.objects.filter(pk=usuario_id).first()
        else:
            user_target = None
        plantas_qs = Planta.objects.filter(usuario=user_target).select_related('especie') if user_target else Planta.objects.none()
        datos = DatosAmbientales.objects.filter(usuario=user_target).first() if user_target else None
    else:
        user_target = request.user
        plantas_qs = Planta.objects.filter(usuario=user_target).select_related('especie')
        datos = DatosAmbientales.objects.filter(usuario=user_target).first()

    plantas = []
    for planta in plantas_qs:
        esta_regando = (planta.estado_servo == 'abierto') or bool(planta.riego_activo)
        plantas.append({
            'id': planta.id,
            'nombre': planta.apodo or (planta.especie.nombre if planta.especie else 'Planta'),
            'mqtt_id': planta.mqtt_id,
            'humedad_actual': getattr(planta, 'humedad_actual', 0.0),
            'umbral_humedad': getattr(planta, 'umbral_humedad', 40.0),
            'estado_servo': 'abierto' if esta_regando else 'cerrado',
            'riego_activo': esta_regando,
            'ultima_lectura': planta.ultima_lectura_mqtt.isoformat() if planta.ultima_lectura_mqtt else None,
            'especie': planta.especie.nombre if planta.especie else 'Sin especie',
            'foto_url': planta.especie.foto.url if planta.especie and planta.especie.foto else None,
        })

    return JsonResponse({
        'plantas': plantas,
        'temperatura': datos.temperatura if (datos and datos.temperatura is not None) else None,
        'humedad_ambiente': datos.humedad_ambiente if (datos and datos.humedad_ambiente is not None) else None,
        'fecha_actualizacion': datos.fecha_actualizacion.isoformat() if (datos and datos.fecha_actualizacion) else None,
    })


@never_cache
def csrf_fallo(request, reason=''):
    return render(request, 'riego/csrf_fallo.html', {'reason': reason}, status=403)


@login_required
@never_cache
def mi_perfil(request):
    perfil, created = PerfilUsuario.objects.get_or_create(user=request.user)
    if perfil.esta_cancelada:
        messages.error(request, 'Tu perfil está deshabilitado por suscripción cancelada. Contactarse con el administrador para solucionar el problema.')
        return redirect('mi_plan')
    if request.method == 'POST':
        perfil.nombre = request.POST.get('nombre', perfil.nombre)
        perfil.cedula = request.POST.get('cedula', perfil.cedula)
        perfil.plan = request.POST.get('plan', perfil.plan)
        if 'foto' in request.FILES:
            perfil.foto = request.FILES['foto']
        perfil.save()
        messages.success(request, 'Perfil actualizado correctamente.')
        return redirect('mi_perfil')
    return render(request, 'riego/perfil.html', {'perfil': perfil})


@staff_member_required
@never_cache
def toggle_respuesta_consulta(request, consulta_id):
    """Marca o desmarca una consulta como respondida."""
    consulta = get_object_or_404(ConsultaContacto, pk=consulta_id)
    consulta.respondido = not consulta.respondido
    consulta.save()
    estado = 'respondida' if consulta.respondido else 'pendiente'
    messages.success(request, f'Consulta de {consulta.nombre} marcada como {estado}.')
    return redirect('admin_dashboard')


@staff_member_required
@never_cache
def eliminar_usuario(request, usuario_id):
    """Elimina un usuario no staff."""
    user = get_object_or_404(User, pk=usuario_id)
    if user.is_staff:
        messages.error(request, 'No se puede eliminar un usuario administrador.')
        return redirect('admin_dashboard')
    if user == request.user:
        messages.error(request, 'No puedes eliminarte a ti mismo.')
        return redirect('admin_dashboard')
    username = user.username
    user.delete()
    messages.success(request, f'Usuario {username} eliminado correctamente.')
    return redirect('admin_dashboard')


@login_required
@never_cache
def mi_plan(request):
    if request.user.is_staff:
        return redirect('admin_dashboard')

    perfil, _ = PerfilUsuario.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        accion = request.POST.get('accion')

        if accion == 'cancelar_suscripcion':
            perfil.estado_suscripcion = PerfilUsuario.EstadoSuscripcion.CANCELADA
            perfil.save(update_fields=['estado_suscripcion'])
            Planta.objects.filter(usuario=request.user).update(riego_activo=False, estado_servo='cerrado')
            messages.error(request, 'Tu suscripción ha sido cancelada. Tus plantas y funciones han sido deshabilitadas. Contactarse con el administrador para solucionar el problema.')
            return redirect('mi_plan')

        elif accion == 'pagar_renovacion':
            referencia = request.POST.get('referencia', '').strip()
            if not referencia:
                messages.error(request, 'Debes ingresar el número de comprobante o referencia de pago.')
                return redirect('mi_plan')

            PagoSuscripcion.objects.create(
                usuario=request.user,
                tipo=PagoSuscripcion.Tipo.RENOVACION,
                plan_solicitado=perfil.plan,
                monto=perfil.precio_plan,
                metodo_pago=request.POST.get('metodo_pago', 'Transferencia Bancaria / PSE'),
                referencia_pago=referencia,
                estado=PagoSuscripcion.Estado.PENDIENTE,
            )
            messages.success(request, 'Pago de renovación reportado. Tan pronto el administrador lo apruebe, se actualizará tu fecha de pago.')
            return redirect('mi_plan')

        elif accion == 'cambiar_plan':
            nuevo_plan = request.POST.get('nuevo_plan')
            referencia = request.POST.get('referencia', '').strip()
            if not nuevo_plan or nuevo_plan not in PerfilUsuario.Plan.values:
                messages.error(request, 'Selecciona un plan válido.')
                return redirect('mi_plan')
            if not referencia:
                messages.error(request, 'Debes ingresar el número de comprobante o referencia de pago para el nuevo plan.')
                return redirect('mi_plan')

            precios = {
                PerfilUsuario.Plan.BASICO: 99000,
                PerfilUsuario.Plan.ESTANDAR: 169000,
                PerfilUsuario.Plan.PREMIUM: 279000,
            }
            monto = precios.get(nuevo_plan, 169000)

            PagoSuscripcion.objects.create(
                usuario=request.user,
                tipo=PagoSuscripcion.Tipo.CAMBIO_PLAN,
                plan_solicitado=nuevo_plan,
                monto=monto,
                metodo_pago=request.POST.get('metodo_pago', 'Transferencia Bancaria / PSE'),
                referencia_pago=referencia,
                estado=PagoSuscripcion.Estado.PENDIENTE,
            )
            messages.success(request, 'Solicitud de cambio de plan enviada con éxito. Tan pronto el administrador la apruebe, tu plan y cupo de plantas se actualizarán.')
            return redirect('mi_plan')

    planes_info = [
        {
            'codigo': PerfilUsuario.Plan.BASICO,
            'nombre': 'Kit Balcón & Ventana (Básico)',
            'precio': 99000,
            'limite': 3,
            'descripcion': 'Perfecto para apartamentos pequeños y macetas de ventana (1 a 3 plantas).',
            'es_actual': perfil.plan == PerfilUsuario.Plan.BASICO,
            'es_mejor': False,
        },
        {
            'codigo': PerfilUsuario.Plan.ESTANDAR,
            'nombre': 'Kit Hogar Verde Pro (Estándar)',
            'precio': 169000,
            'limite': 8,
            'descripcion': 'El sistema más completo para salas, balcones y jardines interiores (4 a 8 plantas).',
            'es_actual': perfil.plan == PerfilUsuario.Plan.ESTANDAR,
            'es_mejor': perfil.plan == PerfilUsuario.Plan.BASICO,
        },
        {
            'codigo': PerfilUsuario.Plan.PREMIUM,
            'nombre': 'Kit Jardín Interior Smart (Premium)',
            'precio': 279000,
            'limite': 16,
            'descripcion': 'El sistema definitivo para hogares grandes, terrazas y coleccionistas (hasta 16 plantas).',
            'es_actual': perfil.plan == PerfilUsuario.Plan.PREMIUM,
            'es_mejor': perfil.plan in [PerfilUsuario.Plan.BASICO, PerfilUsuario.Plan.ESTANDAR],
        },
    ]

    historial_pagos = PagoSuscripcion.objects.filter(usuario=request.user).order_by('-created_at')[:8]
    total_plantas = request.user.planta_set.count()

    dias_restantes = None
    if perfil.fecha_proximo_pago:
        dias_restantes = (perfil.fecha_proximo_pago - timezone.now().date()).days

    return render(request, 'riego/plan.html', {
        'perfil': perfil,
        'planes_info': planes_info,
        'historial_pagos': historial_pagos,
        'total_plantas': total_plantas,
        'limite_alcanzado': total_plantas >= perfil.limite_plantas,
        'dias_restantes': dias_restantes,
    })


@staff_member_required
@require_POST
def admin_aprobar_pago(request, pago_id):
    pago = get_object_or_404(PagoSuscripcion, pk=pago_id)
    perfil, _ = PerfilUsuario.objects.get_or_create(user=pago.usuario)
    perfil.plan = pago.plan_solicitado
    perfil.estado_suscripcion = PerfilUsuario.EstadoSuscripcion.ACTIVA
    perfil.fecha_proximo_pago = timezone.now().date() + timedelta(days=30)
    perfil.save()

    pago.estado = PagoSuscripcion.Estado.APROBADO
    pago.fecha_aprobacion = timezone.now()
    pago.save()

    messages.success(request, f'Pago aprobado. Plan {perfil.get_plan_display()} activado para {pago.usuario.username} con próximo vencimiento el {perfil.fecha_proximo_pago.strftime("%d/%m/%Y")}.')
    return redirect('admin_dashboard')


@staff_member_required
@require_POST
def admin_rechazar_pago(request, pago_id):
    pago = get_object_or_404(PagoSuscripcion, pk=pago_id)
    pago.estado = PagoSuscripcion.Estado.RECHAZADO
    pago.save()
    messages.warning(request, f'Pago rechazado para {pago.usuario.username}.')
    return redirect('admin_dashboard')


@staff_member_required
@require_POST
def admin_reactivar_usuario(request, usuario_id):
    user = get_object_or_404(User, pk=usuario_id)
    perfil, _ = PerfilUsuario.objects.get_or_create(user=user)
    perfil.estado_suscripcion = PerfilUsuario.EstadoSuscripcion.ACTIVA
    perfil.fecha_proximo_pago = timezone.now().date() + timedelta(days=30)
    perfil.save()
    messages.success(request, f'La suscripción y cuenta de {user.username} han sido reactivadas exitosamente.')
    return redirect('admin_dashboard')