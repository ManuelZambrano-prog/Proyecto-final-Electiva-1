from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_GET

from .forms import AsignarPlantaForm, EspecieForm, FotoEspecieForm, HorarioDisponibleForm, NuevaPlantaForm, RegistroForm, UsuarioAdminForm
from .models import Electrovalvula, Especie, HorarioDisponible, PerfilUsuario, Planta, SolicitudPlanta
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
            login(request, user)
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
    return render(request, 'riego/panel.html', {'plantas': plantas_usuario})


@login_required
@never_cache
def nueva_planta(request):
    if request.user.is_staff:
        return redirect('admin_dashboard')
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
    })


@login_required
@require_POST
def toggle_riego(request, planta_id):
    if request.user.is_staff:
        return redirect('admin_dashboard')
    planta = get_object_or_404(Planta, pk=planta_id, usuario=request.user)
    nuevo_estado = not planta.riego_activo
    try:
        publish_plant_command(planta, nuevo_estado)
    except MQTTError as error:
        messages.error(request, f'No se pudo enviar la orden al controlador: {error}')
        return redirect('panel')

    planta.riego_activo = nuevo_estado
    planta.save(update_fields=['riego_activo'])

    electrovalvula, created = Electrovalvula.objects.get_or_create(
        numero_pin=planta.id,
        defaults={'planta': planta, 'esta_activa': planta.riego_activo}
    )
    electrovalvula.planta = planta
    electrovalvula.esta_activa = planta.riego_activo
    electrovalvula.save()

    accion = 'activado' if planta.riego_activo else 'desactivado'
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

    return render(request, 'riego/admin_dashboard.html', {
        'usuarios': usuarios,
        'solicitudes': solicitudes,
        'consultas': consultas,
        'usuario_filtro': usuario_filtro,
        'total_usuarios': usuarios.count(),
        'solicitudes_pendientes': SolicitudPlanta.objects.filter(estado=SolicitudPlanta.Estado.PENDIENTE).count(),
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


@require_GET
def api_datos_plantas(request):
    """Devuelve JSON con estado de plantas y datos ambientales."""
    plantas = []
    for planta in Planta.objects.filter(usuario__is_staff=False).select_related('especie', 'usuario'):
        plantas.append({
            'id': planta.id,
            'nombre': planta.apodo or planta.especie.nombre,
            'mqtt_id': planta.mqtt_id,
            'humedad_actual': getattr(planta, 'humedad_actual', 0.0),
            'temperatura_actual': getattr(planta, 'temperatura_actual', 0.0),
            'umbral_humedad': getattr(planta, 'umbral_humedad', 0.0),
            'estado_servo': getattr(planta, 'estado_servo', 'cerrado'),
            'riego_activo': planta.riego_activo,
            'especie': planta.especie.nombre if planta.especie else 'Sin especie',
            'foto_url': planta.especie.foto.url if planta.especie and planta.especie.foto else None,
        })

    datos = DatosAmbientales.get_datos()
    return JsonResponse({
        'plantas': plantas,
        'temperatura': datos.temperatura,
        'humedad_ambiente': datos.humedad_ambiente,
        'fecha_actualizacion': datos.fecha_actualizacion.isoformat() if datos.fecha_actualizacion else None,
    })


@never_cache
def csrf_fallo(request, reason=''):
    return render(request, 'riego/csrf_fallo.html', {'reason': reason}, status=403)


@login_required
@never_cache
def mi_perfil(request):
    perfil, created = PerfilUsuario.objects.get_or_create(user=request.user)
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