from django.shortcuts import render
from django.utils import timezone
# Create your views here.

def dashboard(request):
    # Lógica para cargar el contenido del dashboard
    context = {
        'now': timezone.now(), # Añade la fecha y hora actual al contexto
    }
    return render(request, 'base.html',context)

def index(request):
    # Lógica para cargar el contenido del índice
    return render(request, 'index.html')