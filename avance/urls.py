# avance/urls.py
from django.urls import path
from . import views

# Sin namespace — compatible con {% url 'avances' %} en base.html
urlpatterns = [
    path('', views.lista_avances, name='avances'),
    path('nuevo/', views.nuevo_avance, name='avance_nuevo'),
    path('importar/', views.upload_view, name='avances_importar'),
    path('plantilla.xlsx', views.descargar_plantilla, name='avances_plantilla'),
    path('upload/', views.upload_redirect, name='avances_upload_legacy'),
    path('<int:avance_id>/', views.detalle_avance, name='avance_detalle'),
    path('<int:avance_id>/editar/', views.editar_avance, name='avance_editar'),
    path('<int:avance_id>/desactivar/', views.desactivar_avance, name='avance_desactivar'),
    path('<int:avance_id>/restaurar/', views.restaurar_avance, name='avance_restaurar'),
    path('<int:avance_id>/vincular/', views.vincular_avance, name='avance_vincular'),
    path('api/parse/', views.parse_file_view, name='avances_api_parse'),
    path('api/import/', views.import_rows_view, name='avances_api_import'),
]
