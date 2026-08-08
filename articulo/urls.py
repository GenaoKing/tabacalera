from django.urls import path

from . import views

urlpatterns = [
    path('', views.lista, name='articulos'),
    path('nuevo/', views.guardar, name='articulo_nuevo'),
    path('<int:articulo_id>/editar/', views.guardar, name='articulo_editar'),
    path('<int:articulo_id>/eliminar/', views.eliminar, name='articulo_eliminar'),
    path('alta-rapida/', views.alta_rapida, name='articulo_alta_rapida'),
]
