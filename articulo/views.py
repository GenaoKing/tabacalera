from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import ArticuloForm
from .models import Articulo


@login_required
def lista(request):
    q = request.GET.get('q', '').strip()
    objetos = Articulo.objects.filter(is_active=True).select_related('proveedor').order_by('descripcion')
    if q:
        objetos = objetos.filter(Q(descripcion__icontains=q) | Q(categoria__icontains=q) | Q(proveedor__nombre__icontains=q))
    return render(request, 'articulos/lista.html', {'objetos': objetos, 'q': q})


@login_required
def guardar(request, articulo_id=None):
    objeto = get_object_or_404(Articulo, pk=articulo_id, is_active=True) if articulo_id else None
    form = ArticuloForm(request.POST or None, instance=objeto)
    if request.method == 'POST' and form.is_valid():
        objeto = form.save()
        messages.success(request, f'Artículo {objeto} guardado correctamente.')
        return redirect('articulos')
    return render(request, 'crud_form.html', {
        'form': form, 'titulo': 'Editar artículo' if objeto else 'Nuevo artículo',
        'volver_url': reverse('articulos'),
    }, status=400 if request.method == 'POST' else 200)


@login_required
@require_POST
def eliminar(request, articulo_id):
    objeto = get_object_or_404(Articulo, pk=articulo_id, is_active=True)
    objeto.delete()
    messages.success(request, f'{objeto} fue desactivado.')
    return redirect('articulos')


@login_required
@require_POST
def alta_rapida(request):
    form = ArticuloForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'success': False, 'errors': form.errors.get_json_data()}, status=400)
    objeto = form.save()
    return JsonResponse({'success': True, 'object': {
        'id': objeto.id, 'descripcion': objeto.descripcion, 'presentacion': objeto.presentacion,
        'categoria': objeto.categoria, 'inventario': 0, 'precio_venta': 0,
    }}, status=201)
