# compra/views.py

import json
from django.forms import inlineformset_factory
from django.shortcuts import render, redirect
from django.db import transaction
from proveedor.models import Proveedor
from .forms import CompraForm, DetalleCompraFormset
from django.http import JsonResponse
from .models import Articulo, Compra, DetalleCompra

def calcular_inventario(articulo_id):
    detalle_compras = DetalleCompra.objects.filter(
        articulo_id=articulo_id,
        is_active=True
    ).order_by('compra__fecha_compra')
    
    total_inventario = sum(detalle.cantidad_restante for detalle in detalle_compras)
    
    return total_inventario

    

def obtener_articulos_por_proveedor(request):
    proveedor_id = request.GET.get('proveedor_id')
    articulos = Articulo.objects.filter(proveedor_id=proveedor_id).values('id', 'descripcion', 'cantidad_minima_orden')
    
    articulos_con_inventario = []
    for articulo in articulos:
        inventario = calcular_inventario(articulo['id'])
        articulo['inventario_restante'] = inventario
        articulos_con_inventario.append(articulo)
    
    return JsonResponse({'articulos': articulos_con_inventario})



def crear_compra(request):
    compra_form = CompraForm()
    proveedores = Proveedor.objects.all()

    if request.method == 'POST':
        print(request.POST)
        compra_form = CompraForm(request.POST)
        detalles_compra_json = request.POST.get('detallesCompra')

        if compra_form.is_valid() and detalles_compra_json:
            with transaction.atomic():
                compra = compra_form.save(commit=False)  # Guarda el formulario sin enviarlo a la base de datos aún
                proveedor_id = request.POST.get('proveedor_id')
                print(proveedor_id)  # Obtiene el valor del proveedor del formulario
                compra.proveedor_id = proveedor_id  # Establece el proveedor_id en el objeto compra
                compra.save()

                detalles_compra = json.loads(detalles_compra_json)
                for detalle in detalles_compra:
                    DetalleCompra.objects.create(
                        compra=compra,
                        articulo_id=detalle['articulo'],
                        cantidad=detalle['cantidad'],
                        precio_compra=detalle['precio_compra'],
                        precio_venta_sugerido=detalle['precio_venta_sugerido'],
                        cantidad_restante=detalle['cantidad']
                    )

            return redirect('/compra/')            

    return render(request, 'compras_form.html', {'form': compra_form, 'proveedores': proveedores})