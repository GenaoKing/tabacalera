from django.urls import path
from .views import *

urlpatterns = [
    path('cosechero/<int:id>',show_cosechero,name='cosecheros_show'),
    path('reporte-cosechero/<int:cosechero_id>/<int:cosecha_id>/', generar_reporte_cosechero, name='reporte_cosechero'),
    path('agregar-entrega-tabaco/<int:cosechero_id>/', agregar_entrega_tabaco, name='agregar_entrega_tabaco'),
    path('',index,name='cosecheros'),

]