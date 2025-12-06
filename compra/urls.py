from django.urls import path
from .views import *

urlpatterns = [
    path('',crear_compra, name='compras'),
    path('obtener-articulos/', obtener_articulos_por_proveedor, name='obtener_articulos'),
    # ... otros patrones de url ...
]
