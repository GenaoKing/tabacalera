from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import ProveedorForm
from .models import Proveedor


@login_required
def lista(request):
    q = request.GET.get('q', '').strip()
    objetos = Proveedor.objects.filter(is_active=True).order_by('nombre')
    if q:
        objetos = objetos.filter(Q(nombre__icontains=q) | Q(correo_electronico__icontains=q))
    return render(request, 'proveedores/lista.html', {'objetos': objetos, 'q': q})


@login_required
def guardar(request, proveedor_id=None):
    objeto = get_object_or_404(Proveedor, pk=proveedor_id, is_active=True) if proveedor_id else None
    form = ProveedorForm(request.POST or None, instance=objeto)
    if request.method == 'POST' and form.is_valid():
        objeto = form.save()
        messages.success(request, f'Proveedor {objeto} guardado correctamente.')
        return redirect('proveedores')
    return render(request, 'crud_form.html', {
        'form': form, 'titulo': 'Editar proveedor' if objeto else 'Nuevo proveedor',
        'volver_url': reverse('proveedores'),
    }, status=400 if request.method == 'POST' else 200)


@login_required
@require_POST
def eliminar(request, proveedor_id):
    objeto = get_object_or_404(Proveedor, pk=proveedor_id, is_active=True)
    objeto.delete()
    messages.success(request, f'{objeto} fue desactivado.')
    return redirect('proveedores')
