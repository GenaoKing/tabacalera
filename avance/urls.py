#urls.py
# avance/urls.py
from django.urls import path
from .views import *

urlpatterns = [
    path('upload/', file_upload_view, name='avances'),
    # ... otros patrones de url ...
]
