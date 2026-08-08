# views.py

import json
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect
from django.db import transaction
from proveedor.models import Proveedor
from .forms import CompraForm
from django.http import JsonResponse
from .models import Articulo, Compra, DetalleCompra
from django.views.decorators.http import require_GET

def calcular_inventario(articulo_id):
    detalle_compras = DetalleCompra.objects.filter(
        articulo_id=articulo_id,
        is_active=True
    ).order_by('compra__fecha_compra')
    
    total_inventario = sum(detalle.cantidad_restante for detalle in detalle_compras)
    
    return total_inventario

    

@login_required
@require_GET
def obtener_articulos_por_proveedor(request):
    proveedor_id = request.GET.get('proveedor_id')
    if not proveedor_id:
        return JsonResponse({'articulos': []})

    articulos = Articulo.objects.filter(
        proveedor_id=proveedor_id,
        is_active=True,
    ).values('id', 'descripcion', 'presentacion', 'cantidad_minima_orden')
    
    articulos_con_inventario = []
    for articulo in articulos:
        inventario = calcular_inventario(articulo['id'])
        articulo['inventario_restante'] = inventario
        articulos_con_inventario.append(articulo)
    
    return JsonResponse({'articulos': articulos_con_inventario})



@login_required
def crear_compra(request):
    compra_form = CompraForm(request.POST if request.method == 'POST' else None)
    proveedores = Proveedor.objects.filter(is_active=True).order_by('nombre')
    proveedor_seleccionado = request.POST.get('proveedor_id', '')
    detalles_compra = []

    if request.method == 'POST':
        detalles_compra_json = request.POST.get('detallesCompra')
        formulario_valido = compra_form.is_valid()
        try:
            detalles_compra = json.loads(detalles_compra_json or '[]')
            if not isinstance(detalles_compra, list):
                raise ValueError
        except json.JSONDecodeError:
            compra_form.add_error(None, 'El detalle de artículos no tiene un formato válido.')
            detalles_compra = []
        except ValueError:
            compra_form.add_error(None, 'El detalle de artículos debe ser una lista.')
            detalles_compra = []

        proveedor = None
        if proveedor_seleccionado:
            proveedor = Proveedor.objects.filter(
                pk=proveedor_seleccionado,
                is_active=True,
            ).first()
        if proveedor is None:
            compra_form.add_error(None, 'Seleccione un proveedor válido.')
        if not detalles_compra:
            compra_form.add_error(None, 'Agregue al menos un artículo a la compra.')

        if formulario_valido and proveedor is not None and detalles_compra:
            with transaction.atomic():
                compra = compra_form.save(commit=False)
                compra.proveedor = proveedor
                compra.save()

                for detalle in detalles_compra:
                    DetalleCompra.objects.create(
                        compra=compra,
                        articulo_id=detalle['articulo'],
                        cantidad=detalle['cantidad'],
                        precio_compra=detalle['precio_compra'],
                        precio_venta_sugerido=detalle['precio_venta_sugerido'],
                        cantidad_restante=detalle['cantidad']
                    )

            messages.success(request, f'Compra {compra.factura} registrada correctamente.')
            return redirect('compras')

    return render(request, 'compras_form.html', {
        'form': compra_form,
        'proveedores': proveedores,
        'proveedor_seleccionado': proveedor_seleccionado,
        'detalles_iniciales': detalles_compra,
    })
