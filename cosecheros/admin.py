from django.contrib import admin
from .models import *
# Register your models here.


admin.site.register(Cosechero)


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