from django.contrib import admin

from ventas.models import *


# Register your models here.
admin.site.register(Venta)
admin.site.register(DetalleArticulo)
admin.site.register(DetalleAvance)