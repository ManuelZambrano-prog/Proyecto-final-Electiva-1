from django.contrib import admin

from .models import Electrovalvula, Especie, HorarioDisponible, Planta, SolicitudPlanta


@admin.register(Especie)
class EspecieAdmin(admin.ModelAdmin):
    list_display = ('nombre',)
    search_fields = ('nombre',)


@admin.register(Planta)
class PlantaAdmin(admin.ModelAdmin):
    list_display = ('apodo', 'especie', 'usuario', 'humedad_actual', 'temperatura_actual', 'riego_activo', 'fecha_agregada')
    list_filter = ('especie', 'usuario', 'riego_activo')


@admin.register(Electrovalvula)
class ElectrovalvulaAdmin(admin.ModelAdmin):
    list_display = ('numero_pin', 'planta', 'esta_activa')
    list_editable = ('esta_activa',)


@admin.register(HorarioDisponible)
class HorarioDisponibleAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'hora', 'disponible')
    list_filter = ('disponible', 'fecha')


@admin.register(SolicitudPlanta)
class SolicitudPlantaAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'especie', 'apodo', 'fecha_cita', 'hora_cita', 'estado', 'created_at')
    list_filter = ('estado', 'especie', 'usuario')
    search_fields = ('usuario__username', 'apodo', 'especie__nombre')
