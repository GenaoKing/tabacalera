"""
ventas/views.py
───────────────
Views delgadas: solo orquestan HTTP request/response.
Toda la lógica de negocio está en services.py.
"""
import json
import logging
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from cosecheros.models import Cosechero, Cosecha

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
        imprimir = (accion == 'imprimir')

        resultado = procesar_venta(
            post_data=request.POST,
            imprimir=False,  # La impresión se maneja aparte
        )

        if resultado['success']:
            venta = resultado['venta']

            if imprimir:
                exito_impresion = _imprimir_ticket(request, venta)
                if exito_impresion:
                    messages.success(request, f'Venta #{venta.id} registrada e impresa.')
                else:
                    messages.warning(
                        request,
                        f'Venta #{venta.id} registrada pero no se pudo imprimir.'
                    )
            else:
                messages.success(request, f'Venta #{venta.id} guardada correctamente.')

            return redirect('ventas')
        else:
            for error in resultado['errors']:
                messages.error(request, error)

    # ── Contexto para GET (o POST fallido) ──
    cosecha_ctx = obtener_contexto_cosecha_default()

    context = {
        'cosecheros': Cosechero.objects.filter(is_active=True).order_by('nombre', 'apellido'),
        'articulos_json': json.dumps(
            obtener_articulos_con_inventario(),
            cls=DjangoJSONEncoder,
        ),
        'cosechas': cosecha_ctx['cosechas'],
        'cosecha_default': cosecha_ctx['cosecha_default'],
        'fecha_hoy': date.today().isoformat(),
    }

    return render(request, 'ventas_form.html', context)


# ─────────────────────────────────────────────
# Tickets
# ─────────────────────────────────────────────

@login_required
@require_GET
def get_tickets(request):
    """Lista todas las ventas activas para la vista de tickets."""
    cosecha_ctx = obtener_contexto_cosecha_default()
    cosecha_id = request.GET.get('cosecha')

    ventas = Venta.objects.filter(is_active=True).select_related(
        'cosechero', 'cosecha'
    ).order_by('-fecha_venta', '-id')

    if cosecha_id:
        ventas = ventas.filter(cosecha_id=cosecha_id)

    context = {
        'ventas': ventas,
        'cosechas': cosecha_ctx['cosechas'],
        'cosecha_default': cosecha_ctx['cosecha_default'],
        'cosecha_seleccionada': int(cosecha_id) if cosecha_id else None,
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
@require_GET
def view_imprimir(request, venta_id: int):
    """Endpoint para imprimir un ticket desde la lista de tickets."""
    venta = get_object_or_404(Venta, pk=venta_id, is_active=True)
    exito = _imprimir_ticket(request, venta)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': exito,
            'message': 'Impreso correctamente' if exito else 'Error al imprimir',
        })

    if exito:
        return HttpResponse(f"Impresión realizada para la venta #{venta_id}")
    return HttpResponse(f"Error al imprimir la venta #{venta_id}", status=500)