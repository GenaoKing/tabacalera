from django.contrib import admin

from compra.models import *

# Register your models here.


class DetalleCompraInline(admin.TabularInline):
    model = DetalleCompra
    extra = 0


@admin.register(Compra)
class CompraAdmin(admin.ModelAdmin):
    inlines = [DetalleCompraInline]