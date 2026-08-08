# avance/urls.py
from django.urls import path
from . import views

# Sin namespace — compatible con {% url 'avances' %} en base.html
urlpatterns = [
    path('upload/', views.upload_view, name='avances'),
    path('api/parse/', views.parse_file_view, name='avances_api_parse'),
    path('api/import/', views.import_rows_view, name='avances_api_import'),
]