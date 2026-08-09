"""
ventas/views.py
───────────────
Views delgadas: solo orquestan HTTP request/response.
Toda la lógica de negocio está en services.py.
"""
import json
import logging
from datetime import date, datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from app.business_dates import proximo_sabado
from articulo.models import Articulo
from cosecheros.models import Cosechero, Cosecha
from proveedor.models import Proveedor

from .models import Venta
from .services import (
    obtener_articulos_con_inventario,
    obtener_contexto_cosecha_default,
    obtener_detalles_venta,
    procesar_venta,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Impresión (se mantiene separada)
# ─────────────────────────────────────────────

def _imprimir_ticket(request, venta: Venta):
    """Intenta imprimir un ticket por USB. Falla silenciosamente si no hay impresora."""
    try:
        from escpos.printer import Usb
        from PIL import Image
        from itertools import groupby

        VID = 0x1FC9
        PID = 0x2016
        logo = Image.open("logo.png")

        p = Usb(idVendor=VID, idProduct=PID)

        p.set(align='center', bold=True)
        p.image(logo)
        p.text("Tabacalera Genao S.R.L\n")

        p.set(align='left', bold=True)
        p.text("Venta ID: ")
        p.set(bold=False)
        p.text(f"{venta.id}             ")

        p.set(bold=True)
        p.text("Vendedor: ")
        p.set(bold=False)
        p.text(f"{request.user.username}\n")

        p.set(bold=True)
        p.text("Cosechero: ")
        p.set(bold=False)
        p.text(f"{venta.cosechero.nombre} {venta.cosechero.apellido}\n")

        p.set(bold=True)
        p.text("Fecha: ")
        p.set(bold=False)
        p.text(f"{venta.fecha_venta.strftime('%d/%m/%Y')}\n")

        # Artículos
        detalles = venta.detalle_articulos.select_related('articulo').all()
        if detalles.exists():
            items = [
                {
                    'articulo': d.articulo,
                    'cantidad': d.cantidad,
                    'precio_venta_final': d.precio_venta_final,
                }
                for d in detalles
            ]
            items.sort(key=lambda x: (x['articulo'].id, x['precio_venta_final']))

            agrupados = []
            for key, group in groupby(items, key=lambda x: (x['articulo'].id, x['precio_venta_final'])):
                gl = list(group)
                agrupados.append({
                    'articulo': gl[0]['articulo'],
                    'precio_venta_final': key[1],
                    'cantidad_total': sum(i['cantidad'] for i in gl),
                })

            p.set(bold=True)
            p.text("\nDetalles de Artículos:\n")
            p.text("Artículo              Cant.   Precio    Subtotal\n")
            p.text("------------------------------------------------\n")
            p.set(bold=False)

            for d in agrupados:
                desc = f"{d['articulo'].presentacion} {d['articulo'].descripcion}"
                p.text(
                    f"{desc[:19]:19} {d['cantidad_total']:5}     "
                    f"{d['precio_venta_final']:5.2f}   "
                    f"{d['cantidad_total'] * d['precio_venta_final']:7.2f}\n"
                )

        # Avances
        avances = venta.detalle_avances.select_related('avance').all()
        if avances.exists():
            p.set(bold=True)
            p.text("\nDetalles de Avances:\n")
            p.text("Tipo      Descripcion         Fecha     Monto\n")
            p.text("------------------------------------------------\n")
            p.set(bold=False)
            for da in avances:
                a = da.avance
                p.text(
                    f"{a.tipo_avance:8}  {a.descripcion:15} "
                    f"{a.fecha.strftime('%d/%m/%Y') if a.fecha else 'N/A':10} "
                    f"{da.monto}\n"
                )

        p.set(bold=True, align='center', double_height=True, double_width=True)
        p.text(f"\nTotal: {venta.total}\n")

        p.set(align='left', bold=False, double_height=False, double_width=False)
        p.text("\n\nRecibido por:\n\n")
        p.text("_____________________________________________\n")
        p.ln(count=15)
        p.cut()
        p.close()

        venta.impreso = True
        venta.save(update_fields=['impreso'])
        return True

    except Exception as e:
        logger.error(f"Error al imprimir venta #{venta.id}: {e}")
        return False


# ─────────────────────────────────────────────
# Vista principal: Registro de Venta
# ─────────────────────────────────────────────

@login_required
@require_http_methods(["GET", "POST"])
def registrar_venta(request):
    """
    GET:  Renderiza el formulario de venta con artículos e inventario.
    POST: Procesa la venta (guardar o registrar+imprimir).
    """
    if request.method == 'POST':
        accion = request.POST.get('accion', 'guardar')
        imprimir = accion == 'imprimir'

        resultado = procesar_venta(
            post_data=request.POST,
            imprimir=imprimir,
            idempotency_key=request.headers.get('Idempotency-Key'),
            usuario=request.user,
        )

        quiere_json = (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or 'application/json' in request.headers.get('Accept', '')
        )

        if resultado['success']:
            venta = resultado['venta']

            if quiere_json:
                return JsonResponse({
                    'success': True,
                    'venta_id': venta.id,
                    'operacion': str(resultado['operacion'].clave),
                    'replayed': resultado.get('replayed', False),
                    'total_semanal': f'{venta.total:.2f}',
                    'impreso': venta.impreso,
                    'print_url': request.build_absolute_uri(
                        f'/ventas/imprimir/{venta.id}/'
                    ),
                    'message': (
                        'La operación ya estaba registrada.'
                        if resultado.get('replayed')
                        else f'Venta #{venta.id} guardada.'
                    ),
                })

            messages.success(request, f'Venta #{venta.id} guardada correctamente.')

            return redirect('ventas')
        else:
            if quiere_json:
                return JsonResponse(
                    {'success': False, 'errors': resultado['errors']},
                    status=409 if resultado.get('idempotency_conflict') else 400,
                )
            for error in resultado['errors']:
                messages.error(request, error)

    # ── Contexto para GET (o POST fallido) ──
    cosecha_ctx = obtener_contexto_cosecha_default()

    context = {
        'cosecheros_json': json.dumps([
            {
                'id': cosechero.id,
                'nombre': f'{cosechero.nombre} {cosechero.apellido}'.strip(),
            }
            for cosechero in Cosechero.objects.filter(is_active=True).order_by('nombre', 'apellido')
        ], cls=DjangoJSONEncoder),
        'articulos_json': json.dumps(
            obtener_articulos_con_inventario(),
            cls=DjangoJSONEncoder,
        ),
        'cosechas': cosecha_ctx['cosechas'],
        'cosecha_default': cosecha_ctx['cosecha_default'],
        'fecha_hoy': date.today().isoformat(),
        'usuario_id': request.user.id,
        'proveedores_json': json.dumps([
            {'id': proveedor.id, 'nombre': proveedor.nombre}
            for proveedor in Proveedor.objects.filter(is_active=True).order_by('nombre')
        ], cls=DjangoJSONEncoder),
        'categorias_json': json.dumps([
            {'valor': valor, 'nombre': nombre}
            for valor, nombre in Articulo.CATEGORIAS_CHOICES
        ], cls=DjangoJSONEncoder),
    }

    return render(request, 'ventas_form_v2.html', context)


# ─────────────────────────────────────────────
# Tickets
# ─────────────────────────────────────────────

@login_required
@require_GET
def get_tickets(request):
    """Lista ventas activas, filtradas y paginadas en el servidor."""
    cosecha_ctx = obtener_contexto_cosecha_default()
    cosecha_id = request.GET.get('cosecha')

    ventas = Venta.objects.filter(is_active=True).select_related(
        'cosechero', 'cosecha'
    ).order_by('-fecha_venta', '-id')

    if cosecha_id:
        ventas = ventas.filter(cosecha_id=cosecha_id)

    q = request.GET.get('q', '').strip()
    desde = request.GET.get('desde', '').strip()
    hasta = request.GET.get('hasta', '').strip()
    if q:
        ventas = ventas.filter(
            Q(cosechero__nombre__icontains=q)
            | Q(cosechero__apellido__icontains=q)
        )
    if desde:
        ventas = ventas.filter(fecha_venta__gte=desde)
    if hasta:
        ventas = ventas.filter(fecha_venta__lte=hasta)

    pagina = Paginator(ventas, 50).get_page(request.GET.get('page'))
    filtros = request.GET.copy()
    filtros.pop('page', None)

    context = {
        'ventas': pagina.object_list,
        'page_obj': pagina,
        'cosechas': cosecha_ctx['cosechas'],
        'cosecha_default': cosecha_ctx['cosecha_default'],
        'cosecha_seleccionada': int(cosecha_id) if cosecha_id else None,
        'q': q,
        'desde': desde,
        'hasta': hasta,
        'filtros_query': filtros.urlencode(),
    }
    return render(request, 'tickets.html', context)


# ─────────────────────────────────────────────
# API: Detalles de venta (JSON)
# ─────────────────────────────────────────────

@login_required
@require_GET
def detalles_venta(request, venta_id: int):
    """Retorna los detalles de una venta en JSON para el modal."""
    venta = get_object_or_404(Venta, pk=venta_id, is_active=True)
    data = obtener_detalles_venta(venta)
    return JsonResponse(data)


# ─────────────────────────────────────────────
# Impresión desde tickets
# ─────────────────────────────────────────────

@login_required
@require_POST
def view_imprimir(request, venta_id: int):
    """Endpoint para imprimir un ticket desde la lista de tickets."""
    venta = get_object_or_404(Venta, pk=venta_id, is_active=True)
    exito = _imprimir_ticket(request, venta)

    return JsonResponse({
        'success': exito,
        'venta_id': venta.id,
        'impreso': venta.impreso,
        'message': 'Impreso correctamente' if exito else 'La venta está guardada, pero falló la impresión.',
    }, status=200 if exito else 503)


@login_required
@require_GET
def resumen_semanal(request):
    """Resume la cuenta semanal exacta de la selección del formulario."""
    try:
        cosechero_id = int(request.GET.get('cosechero', ''))
        cosecha_id = int(request.GET.get('cosecha', ''))
        fecha = datetime.strptime(request.GET.get('fecha', ''), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return JsonResponse({'errors': ['Selección semanal incompleta.']}, status=400)

    sabado = proximo_sabado(fecha)
    ventas = Venta.objects.filter(
        cosechero_id=cosechero_id,
        cosecha_id=cosecha_id,
        fecha_venta=sabado,
        is_active=True,
    ).order_by('id')
    if ventas.count() > 1:
        return JsonResponse({
            'errors': ['Esta semana contiene tickets históricos duplicados y no admite movimientos nuevos.'],
            'sabado': sabado.isoformat(),
            'ambigua': True,
        }, status=409)
    venta = ventas.first()
    return JsonResponse({
        'sabado': sabado.isoformat(),
        'existe': venta is not None,
        'venta_id': venta.id if venta else None,
        'total': f'{venta.total:.2f}' if venta else '0.00',
        'impreso': venta.impreso if venta else False,
    })
