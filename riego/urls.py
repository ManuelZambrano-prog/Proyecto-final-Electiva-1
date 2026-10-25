from django.urls import path

from . import views

urlpatterns = [
    path('inicio/', views.home, name='home'),
    path('panel/', views.panel_usuario, name='panel'),
    path('panel/api/', views.api_datos_plantas, name='api_datos_plantas'),
    path('register/', views.registro, name='register'),
    path('perfil/', views.mi_perfil, name='mi_perfil'),
    path('plan/', views.mi_plan, name='mi_plan'),
    path('nueva-planta/', views.nueva_planta, name='nueva_planta'),
    path('toggle-riego/<int:planta_id>/', views.toggle_riego, name='toggle_riego'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-crear-usuario/', views.admin_crear_usuario, name='admin_crear_usuario'),
    path('admin-horarios/', views.admin_horarios, name='admin_horarios'),
    path('admin-agregar-planta/', views.admin_agregar_planta, name='admin_agregar_planta'),
    path('admin-aprobar-pago/<int:pago_id>/', views.admin_aprobar_pago, name='admin_aprobar_pago'),
    path('admin-rechazar-pago/<int:pago_id>/', views.admin_rechazar_pago, name='admin_rechazar_pago'),
    path('admin-reactivar-usuario/<int:usuario_id>/', views.admin_reactivar_usuario, name='admin_reactivar_usuario'),
    path('admin-toggle-respuesta/<int:consulta_id>/', views.toggle_respuesta_consulta, name='toggle_respuesta_consulta'),
    path('admin-eliminar-usuario/<int:usuario_id>/', views.eliminar_usuario, name='eliminar_usuario'),
]
