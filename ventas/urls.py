from django.urls import path
from .views import *

urlpatterns = [
    path('', registrar_venta, name='ventas'),
    path('tickets', get_tickets, name='tickets'),
    path('detalles/<int:venta_id>/', detalles_venta, name='detalles_venta'),
    path('imprimir/<int:venta_id>/', view_imprimir, name='view_imprimir'),
    # ... otros patrones de url ...
    
]
