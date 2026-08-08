from django.urls import path

from . import views

urlpatterns = [
    path('', views.lista, name='proveedores'),
    path('nuevo/', views.guardar, name='proveedor_nuevo'),
    path('<int:proveedor_id>/editar/', views.guardar, name='proveedor_editar'),
    path('<int:proveedor_id>/eliminar/', views.eliminar, name='proveedor_eliminar'),
]
