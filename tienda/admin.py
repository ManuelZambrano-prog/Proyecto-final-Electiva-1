from django.contrib import admin
from .models import KitRiego, Pedido, ConsultaContacto, Testimonio


@admin.register(KitRiego)
class KitRiegoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'precio', 'plantas_recomendadas', 'valvulas_incluidas', 'destacado', 'orden')
    list_editable = ('precio', 'destacado', 'orden')
    prepopulated_fields = {'slug': ('nombre',)}
    search_fields = ('nombre', 'subtitulo')


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre_completo', 'kit', 'ciudad', 'total', 'metodo_pago', 'estado', 'creado_en')
    list_filter = ('estado', 'metodo_pago', 'creado_en', 'kit')
    search_fields = ('codigo', 'nombre_completo', 'email', 'telefono', 'ciudad')
    readonly_fields = ('codigo', 'creado_en', 'total')


@admin.register(ConsultaContacto)
class ConsultaContactoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'email', 'telefono', 'tipo_consulta', 'creado_en', 'respondido')
    list_filter = ('tipo_consulta', 'respondido', 'creado_en')
    list_editable = ('respondido',)
    search_fields = ('nombre', 'email', 'mensaje')


@admin.register(Testimonio)
class TestimonioAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'ubicacion', 'plantas', 'estrellas', 'activo')
    list_editable = ('activo', 'estrellas')
