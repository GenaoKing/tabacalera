# avance/urls.py
from django.urls import path
from . import views

app_name = 'avances'

urlpatterns = [
    path('upload/', views.upload_view, name='upload'),
    path('api/parse/', views.parse_file_view, name='api_parse'),
    path('api/import/', views.import_rows_view, name='api_import'),
]