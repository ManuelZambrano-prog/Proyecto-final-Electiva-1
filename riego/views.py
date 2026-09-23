from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render

from .forms import HorarioDisponibleForm, NuevaPlantaForm, RegistroForm, UsuarioAdminForm
from .models import Electrovalvula, HorarioDisponible, PerfilUsuario, Planta, SolicitudPlanta


@login_required
def home(request):
    if request.user.is_staff:
        return redirect('admin_dashboard')
    return redirect('panel')


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
def panel_usuario(request):
    if request.user.is_staff:
        return redirect('admin_dashboard')
    plantas_usuario = Planta.objects.filter(usuario=request.user).select_related('especie').order_by('-fecha_agregada')
    return render(request, 'riego/panel.html', {'plantas': plantas_usuario})


@login_required
def nueva_planta(request):
    if request.user.is_staff:
        return redirect('admin_dashboard')
    if request.method == 'POST':
        form = NuevaPlantaForm(request.POST)
        if form.is_valid():
            solicitud = form.save(commit=False)
            solicitud.usuario = request.user
            solicitud.estado = SolicitudPlanta.Estado.PENDIENTE
            solicitud.save()

            slot = HorarioDisponible.objects.get(fecha=form.cleaned_data['fecha_cita'], hora=form.cleaned_data['hora_cita'])
            slot.disponible = False
            slot.save()

            messages.success(request, 'Tu solicitud para agregar la planta fue enviada correctamente.')
            return redirect('panel')
    else:
        form = NuevaPlantaForm()

    return render(request, 'riego/nueva_planta.html', {'form': form})


@login_required
def toggle_riego(request, planta_id):
    if request.user.is_staff:
        return redirect('admin_dashboard')
    planta = get_object_or_404(Planta, pk=planta_id, usuario=request.user)
    planta.riego_activo = not planta.riego_activo
    planta.save()

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
def admin_dashboard(request):
    usuarios = User.objects.filter(is_staff=False).order_by('username')
    solicitudes = SolicitudPlanta.objects.select_related('usuario', 'especie').order_by('-created_at')

    usuario_filtro = request.GET.get('usuario')
    if usuario_filtro:
        solicitudes = solicitudes.filter(usuario_id=usuario_filtro)

    if request.method == 'POST':
        solicitud_id = request.POST.get('solicitud_id')
        nueva_estado = request.POST.get('estado')
        if solicitud_id and nueva_estado:
            solicitud = get_object_or_404(SolicitudPlanta, pk=solicitud_id)
            solicitud.estado = nueva_estado
            solicitud.save()

            if nueva_estado == SolicitudPlanta.Estado.APROBADA:
                Planta.objects.get_or_create(
                    usuario=solicitud.usuario,
                    especie=solicitud.especie,
                    apodo=solicitud.apodo or solicitud.especie.nombre,
                    defaults={'humedad_actual': 0.0, 'temperatura_actual': 0.0}
                )
                messages.success(request, f'Solicitud aprobada para {solicitud.usuario.username}.')
            elif nueva_estado == SolicitudPlanta.Estado.RECHAZADA:
                messages.warning(request, f'Solicitud rechazada para {solicitud.usuario.username}.')

            return redirect('admin_dashboard')

    return render(request, 'riego/admin_dashboard.html', {
        'usuarios': usuarios,
        'solicitudes': solicitudes,
        'usuario_filtro': usuario_filtro,
        'total_usuarios': usuarios.count(),
        'solicitudes_pendientes': SolicitudPlanta.objects.filter(estado=SolicitudPlanta.Estado.PENDIENTE).count(),
        'horarios_disponibles': HorarioDisponible.objects.filter(disponible=True).count(),
    })


@staff_member_required
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
def admin_horarios(request):
    if request.method == 'POST':
        form = HorarioDisponibleForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Horario disponible registrado correctamente.')
            return redirect('admin_horarios')
    else:
        form = HorarioDisponibleForm()

    horarios = HorarioDisponible.objects.order_by('fecha', 'hora')
    return render(request, 'riego/admin_horarios.html', {'form': form, 'horarios': horarios})
