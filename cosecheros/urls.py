from django.urls import path
from .views import *

urlpatterns = [
    path('cosechero/<int:id>',show_cosechero,name='cosecheros_show'),
    path('reporte-cosechero/<int:cosechero_id>/<int:cosecha_id>/', generar_reporte_cosechero, name='reporte_cosechero'),
    path('agregar-entrega-tabaco/<int:cosechero_id>/', agregar_entrega_tabaco, name='agregar_entrega_tabaco'),
    path('precios/', gestionar_precios, name='precios'),
    path('nuevo/', guardar_cosechero, name='cosechero_nuevo'),
    path('<int:cosechero_id>/editar/', guardar_cosechero, name='cosechero_editar'),
    path('<int:cosechero_id>/eliminar/', eliminar_cosechero, name='cosechero_eliminar'),
    path('alta-rapida/', alta_rapida_cosechero, name='cosechero_alta_rapida'),
    path('',index,name='cosecheros'),

]
