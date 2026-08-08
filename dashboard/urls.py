from django.urls import path
from .views import dashboard, exportar_csv

urlpatterns = [
    path('', dashboard, name='dashboard'),
    path('exportar.csv', exportar_csv, name='dashboard_csv'),
    # ... otros patrones de url ...
]
