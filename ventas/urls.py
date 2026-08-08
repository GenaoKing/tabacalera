"""
ventas/urls.py
"""
from django.urls import path
from . import views

urlpatterns = [
    path('', views.registrar_venta, name='ventas'),
    path('tickets/', views.get_tickets, name='tickets'),
    path('detalles/<int:venta_id>/', views.detalles_venta, name='detalles_venta'),
    path('imprimir/<int:venta_id>/', views.view_imprimir, name='view_imprimir'),
]