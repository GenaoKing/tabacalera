from django.contrib import admin

from .models import Cosechero, EntregaTabaco, PrecioVariedadCosecha


@admin.register(Cosechero)
class CosecheroAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'apellido', 'telefono', 'terreno_sembrado', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('=id', 'nombre', 'apellido', 'cedula', 'telefono')
    ordering = ('nombre', 'apellido')
    list_per_page = 50


@admin.register(EntregaTabaco)
class EntregaTabacoAdmin(admin.ModelAdmin):
    list_display = ('id', 'fecha_entrega', 'cosechero', 'cosecha', 'variedad')
    list_filter = ('cosecha', 'variedad', 'fecha_entrega')
    search_fields = (
        '=id', '=cosechero__id', 'cosechero__nombre', 'cosechero__apellido',
    )
    autocomplete_fields = ('cosechero',)
    list_select_related = ('cosechero', 'cosecha')
    date_hierarchy = 'fecha_entrega'
    ordering = ('-id',)
    list_per_page = 50


@admin.register(PrecioVariedadCosecha)
class PrecioVariedadCosechaAdmin(admin.ModelAdmin):
    list_display = (
        'cosecha', 'variedad',
        'precio_centro_largo', 'precio_centro_corto', 'precio_uno_medio',
        'precio_libre_pie', 'precio_picadura', 'precio_rezago', 'precio_criollo',
    )
    list_filter = ('cosecha', 'variedad')
    list_editable = (
        'precio_centro_largo', 'precio_centro_corto', 'precio_uno_medio',
        'precio_libre_pie', 'precio_picadura', 'precio_rezago', 'precio_criollo',
    )
