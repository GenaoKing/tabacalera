import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from articulo.models import Articulo
from proveedor.models import Proveedor

from .forms import CompraForm
from .services import (
    CompraDuplicada,
    DetallesCompraInvalidos,
    ProveedorCompraInvalido,
    catalogo_articulos_por_proveedor,
    registrar_compra,
)


def _entero_o_none(valor):
    if isinstance(valor, bool):
        return None
    try:
        return int(str(valor))
    except (TypeError, ValueError):
        return None


def _detalles_para_render(detalles, errores_por_linea):
    ids = {
        articulo_id
        for detalle in detalles
        if isinstance(detalle, dict)
        for articulo_id in [_entero_o_none(detalle.get('articulo'))]
        if articulo_id is not None
    }
    articulos = {
        articulo['id']: articulo
        for articulo in Articulo.objects.filter(pk__in=ids).values(
            'id',
            'descripcion',
            'presentacion',
            'categoria',
            'cantidad_minima_orden',
            'is_active',
            'proveedor_id',
        )
    }

    resultado = []
    for indice, detalle in enumerate(detalles):
        detalle = detalle if isinstance(detalle, dict) else {}
        articulo_id = _entero_o_none(detalle.get('articulo'))
        articulo = articulos.get(articulo_id, {})
        resultado.append({
            'articulo': detalle.get('articulo'),
            'cantidad': detalle.get('cantidad', ''),
            'precio_compra': detalle.get('precio_compra', ''),
            'precio_venta_sugerido': detalle.get('precio_venta_sugerido', ''),
            'descripcion': articulo.get('descripcion') or f'Artículo #{articulo_id or "inválido"}',
            'presentacion': articulo.get('presentacion') or 'No disponible',
            'categoria': articulo.get('categoria') or '',
            'cantidad_minima_orden': articulo.get('cantidad_minima_orden', 0),
            'is_active': articulo.get('is_active', False),
            'proveedor_id': articulo.get('proveedor_id'),
            'errores': errores_por_linea.get(indice, []),
        })
    return resultado


@login_required
@require_GET
def obtener_articulos_por_proveedor(request):
    proveedor_id = request.GET.get('proveedor_id')
    if not proveedor_id:
        return JsonResponse({'articulos': []})

    return JsonResponse({
        'articulos': list(catalogo_articulos_por_proveedor(proveedor_id)),
    })


@login_required
def crear_compra(request):
    compra_form = CompraForm(request.POST if request.method == 'POST' else None)
    proveedores = Proveedor.objects.filter(is_active=True).order_by('nombre')
    proveedor_seleccionado = request.POST.get('proveedor_id', '')
    detalles_compra = []
    errores_por_linea = {}
    respuesta_invalida = False

    if request.method == 'POST':
        formulario_valido = compra_form.is_valid()
        detalles_compra_json = request.POST.get('detallesCompra')
        try:
            detalles_compra = json.loads(detalles_compra_json or '[]')
            if not isinstance(detalles_compra, list):
                raise ValueError
        except json.JSONDecodeError:
            compra_form.add_error(None, 'El detalle de artículos no tiene un formato válido.')
            detalles_compra = []
            respuesta_invalida = True
        except ValueError:
            compra_form.add_error(None, 'El detalle de artículos debe ser una lista.')
            detalles_compra = []
            respuesta_invalida = True

        if not proveedor_seleccionado:
            compra_form.add_error(None, 'Seleccione un proveedor válido.')
            respuesta_invalida = True
        if not detalles_compra:
            compra_form.add_error(None, 'Agregue al menos un artículo a la compra.')
            respuesta_invalida = True

        if formulario_valido and not respuesta_invalida:
            try:
                compra = registrar_compra(
                    compra_form,
                    proveedor_seleccionado,
                    detalles_compra,
                )
            except ProveedorCompraInvalido:
                compra_form.add_error(None, 'Seleccione un proveedor válido.')
                respuesta_invalida = True
            except CompraDuplicada:
                compra_form.add_error(
                    'factura',
                    'Ya existe una compra de este proveedor con la misma factura.',
                )
                respuesta_invalida = True
            except DetallesCompraInvalidos as error:
                errores_por_linea = error.errores_por_linea
                compra_form.add_error(None, 'Revise las líneas señaladas de la compra.')
                respuesta_invalida = True
            else:
                messages.success(
                    request,
                    f'Compra {compra.factura} registrada correctamente.',
                )
                return redirect(f'{reverse("compras")}?guardada=1')
        else:
            respuesta_invalida = True

    detalles_iniciales = _detalles_para_render(detalles_compra, errores_por_linea)
    cabecera_inicial = {
        nombre: compra_form[nombre].value() or ''
        for nombre in compra_form.fields
    }
    return render(request, 'compras_form.html', {
        'form': compra_form,
        'proveedores': proveedores,
        'proveedor_seleccionado': proveedor_seleccionado,
        'detalles_iniciales': detalles_iniciales,
        'usuario_id': request.user.id,
        'categorias_articulo': Articulo.CATEGORIAS_CHOICES,
        'cabecera_inicial': cabecera_inicial,
        'compra_guardada': request.GET.get('guardada') == '1',
        'es_post': request.method == 'POST',
    }, status=400 if respuesta_invalida else 200)
