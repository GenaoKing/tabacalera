"""
ventas/services.py
──────────────────
Capa de servicios para el módulo de ventas.
Toda la lógica de negocio vive aquí, las views solo orquestan HTTP.
"""
import decimal
import logging
from datetime import date, timedelta
from decimal import Decimal
from itertools import groupby
from typing import Optional

from django.db import transaction
from django.db.models import Sum

from articulo.models import Articulo
from avance.models import Avance
from compra.models import DetalleCompra
from cosecheros.models import Cosechero, Cosecha

from .models import Venta, DetalleArticulo, DetalleAvance

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Utilidades de fecha (sábado = cierre semanal)
# ─────────────────────────────────────────────

def proximo_sabado(fecha_venta: date) -> date:
    """
    Retorna el próximo sábado (o el mismo día si es sábado).
    Las ventas se computan los sábados — los items se acumulan durante la semana.
    """
    dias_hasta_sabado = (5 - fecha_venta.weekday()) % 7
    if dias_hasta_sabado == 0:
        return fecha_venta
    return fecha_venta + timedelta(days=dias_hasta_sabado)


def obtener_venta_existente(cosechero_id: int, fecha_sabado: date) -> Optional[Venta]:
    """Busca una venta existente para el cosechero en la semana de fecha_sabado."""
    inicio_semana = fecha_sabado - timedelta(days=fecha_sabado.weekday())
    fin_semana = inicio_semana + timedelta(days=6)
    return Venta.objects.filter(
        cosechero_id=cosechero_id,
        fecha_venta__range=(inicio_semana, fin_semana),
        is_active=True,
    ).first()


# ─────────────────────────────────────────────
# Inventario y precios (FIFO por lotes)
# ─────────────────────────────────────────────

def calcular_inventario_articulo(articulo_id: int) -> Decimal:
    """Retorna el inventario total disponible para un artículo."""
    return DetalleCompra.objects.filter(
        articulo_id=articulo_id,
        cantidad_restante__gt=0,
        compra__is_active=True,
        is_active=True,
    ).aggregate(
        total=Sum('cantidad_restante')
    )['total'] or Decimal('0')


def obtener_articulos_con_inventario() -> list[dict]:
    """
    Retorna todos los artículos activos con inventario total y precio FIFO
    (precio del lote más antiguo con existencia).

    Usa un número constante de consultas (3) independientemente de la
    cantidad de artículos, en vez de una consulta a DetalleCompra por
    cada artículo.
    """
    articulos = Articulo.objects.filter(is_active=True).order_by('descripcion')

    lotes_disponibles = DetalleCompra.objects.filter(
        cantidad_restante__gt=0,
        compra__is_active=True,
        is_active=True,
    ).order_by('articulo_id', 'compra__fecha_compra')

    inventario_map = {
        fila['articulo_id']: fila['total']
        for fila in lotes_disponibles.values('articulo_id').annotate(total=Sum('cantidad_restante'))
    }

    precio_map = {}
    for lote in lotes_disponibles.values('articulo_id', 'precio_venta_sugerido'):
        precio_map.setdefault(lote['articulo_id'], lote['precio_venta_sugerido'])

    resultado = []
    for articulo in articulos:
        resultado.append({
            'id': articulo.id,
            'descripcion': articulo.descripcion,
            'categoria': articulo.categoria,
            'presentacion': getattr(articulo, 'presentacion', ''),
            'inventario': float(inventario_map.get(articulo.id, 0)),
            'precio_venta': float(precio_map.get(articulo.id, 0)),
        })

    return resultado


def consumir_lotes_fifo(articulo_id: int, cantidad_solicitada) -> list[dict]:
    """
    Consume inventario FIFO y retorna los lotes usados.
    Cada lote incluye: compra_id, cantidad, precio_venta.
    """
    lotes_usados = []
    restante = Decimal(str(cantidad_solicitada))

    detalles = DetalleCompra.objects.filter(
        articulo_id=articulo_id,
        cantidad_restante__gt=0,
        compra__is_active=True,
        is_active=True,
    ).select_for_update().order_by('compra__fecha_compra')

    for detalle in detalles:
        if restante <= 0:
            break

        disponible = detalle.cantidad_restante
        consumido = min(disponible, restante)

        lotes_usados.append({
            'compra_id': detalle.compra_id,
            'cantidad': consumido,
            'precio_venta': detalle.precio_venta_sugerido,
        })

        detalle.cantidad_restante -= consumido
        detalle.save(update_fields=['cantidad_restante'])
        restante -= consumido

    if restante > 0:
        logger.warning(
            f"Inventario insuficiente para artículo {articulo_id}: "
            f"faltaron {restante} unidades"
        )

    return lotes_usados


# ─────────────────────────────────────────────
# Validación de inventario
# ─────────────────────────────────────────────

def validar_inventario_suficiente(items: list[dict]) -> list[str]:
    """
    Recibe lista de {'articulo_id': int, 'cantidad': Decimal}.
    Retorna lista de errores (vacía si todo OK).
    """
    errores = []
    for item in items:
        inv = calcular_inventario_articulo(item['articulo_id'])
        if inv < Decimal(str(item['cantidad'])):
            try:
                art = Articulo.objects.get(id=item['articulo_id'])
                nombre = art.descripcion
            except Articulo.DoesNotExist:
                nombre = f"ID {item['articulo_id']}"
            errores.append(
                f"Inventario insuficiente para {nombre}: "
                f"disponible {inv}, solicitado {item['cantidad']}"
            )
    return errores


# ─────────────────────────────────────────────
# Creación de avances desde formulario
# ─────────────────────────────────────────────

def extraer_avances_validados(post_data: dict) -> tuple[list[dict], list[str]]:
    """
    Extrae y valida las filas de avance del POST.
    Retorna (avances_data, errores). Si hay errores, no debe crearse nada:
    el llamador debe abortar el submit completo antes de tocar la BD.
    """
    total_forms = int(post_data.get('detalle_avances-TOTAL_FORMS', 0))
    avances_data = []
    errores = []

    for i in range(total_forms):
        descripcion = post_data.get(f'detalle_avances-{i}-descripcion', '').strip()
        tipo_avance = post_data.get(f'detalle_avances-{i}-tipo_avance', '').strip()
        numero = post_data.get(f'detalle_avances-{i}-numero', '').strip()
        monto = post_data.get(f'detalle_avances-{i}-monto', '').strip()
        estado = post_data.get(f'detalle_avances-{i}-estado', 'realizado').strip()
        fecha = post_data.get(f'detalle_avances-{i}-fecha', '').strip()

        faltantes = [
            etiqueta for etiqueta, valor in (
                ('tipo', tipo_avance), ('número', numero),
                ('monto', monto), ('fecha', fecha),
            ) if not valor
        ]
        if faltantes:
            errores.append(f"Avance #{i + 1}: falta {', '.join(faltantes)}.")
            continue

        avances_data.append({
            'descripcion': descripcion or f"Avance {tipo_avance} #{numero}",
            'tipo_avance': tipo_avance,
            'numero': numero,
            'monto_pagado': Decimal(monto),
            'estado': estado,
            'fecha': fecha,
        })

    return avances_data, errores


def crear_avances(avances_data: list[dict], cosechero: Cosechero) -> list[Avance]:
    """Crea objetos Avance a partir de datos ya validados por extraer_avances_validados."""
    return [
        Avance.objects.create(cosechero=cosechero, **data)
        for data in avances_data
    ]


# ─────────────────────────────────────────────
# Procesamiento completo de venta
# ─────────────────────────────────────────────

def _extraer_items_articulo(post_data: dict) -> list[dict]:
    """Extrae los items de artículo del POST data."""
    total = int(post_data.get('detalle_articulos-TOTAL_FORMS', 0))
    items = []

    for i in range(total):
        articulo_id = post_data.get(f'detalle_articulos-{i}-articulo')
        cantidad = post_data.get(f'detalle_articulos-{i}-cantidad')

        if articulo_id and cantidad:
            items.append({
                'articulo_id': int(articulo_id),
                'cantidad': Decimal(str(cantidad)),
            })

    return items


@transaction.atomic
def procesar_venta(post_data: dict, imprimir: bool = False) -> dict:
    """
    Procesa una venta completa:
    1. Valida inventario
    2. Crea o reutiliza la venta semanal
    3. Consume lotes FIFO y crea DetalleArticulo
    4. Crea Avances y DetalleAvance
    5. Recalcula total

    Retorna: {'success': bool, 'venta': Venta|None, 'errors': list}
    """
    # ── Extraer datos básicos ──
    cosechero_id = int(post_data.get('cosechero', 0))
    cosecha_id = int(post_data.get('cosecha', 0))
    fecha_raw = post_data.get('fecha_venta', '')

    if not all([cosechero_id, cosecha_id, fecha_raw]):
        return {'success': False, 'venta': None, 'errors': ['Datos incompletos']}

    try:
        cosechero = Cosechero.objects.get(id=cosechero_id)
        cosecha = Cosecha.objects.get(id=cosecha_id)
    except (Cosechero.DoesNotExist, Cosecha.DoesNotExist) as e:
        return {'success': False, 'venta': None, 'errors': [str(e)]}

    # ── Parsear fecha y calcular sábado ──
    from datetime import datetime
    try:
        fecha_venta = datetime.strptime(fecha_raw, '%Y-%m-%d').date()
    except ValueError:
        return {'success': False, 'venta': None, 'errors': ['Fecha inválida']}

    fecha_sabado = proximo_sabado(fecha_venta)

    # ── Extraer y validar items ──
    items = _extraer_items_articulo(post_data)

    if items:
        errores_inv = validar_inventario_suficiente(items)
        if errores_inv:
            return {'success': False, 'venta': None, 'errors': errores_inv}

    # ── Extraer y validar avances (antes de tocar la BD) ──
    avances_data, errores_avance = extraer_avances_validados(post_data)
    if errores_avance:
        return {'success': False, 'venta': None, 'errors': errores_avance}

    # ── Obtener o crear venta ──
    venta_existente = obtener_venta_existente(cosechero_id, fecha_sabado)

    if venta_existente:
        venta = venta_existente
    else:
        venta = Venta.objects.create(
            cosechero=cosechero,
            cosecha=cosecha,
            fecha_venta=fecha_sabado,
            total=Decimal('0'),
            impreso=imprimir,
        )

    # ── Crear detalles de artículos (FIFO) ──
    # bulk_create no dispara señales post_save por fila: evita recalcular
    # el total de la venta una vez por cada lote consumido.
    detalles_articulo = []
    for item in items:
        lotes = consumir_lotes_fifo(item['articulo_id'], item['cantidad'])
        for lote in lotes:
            detalles_articulo.append(DetalleArticulo(
                venta=venta,
                articulo_id=item['articulo_id'],
                cantidad=lote['cantidad'],
                precio_venta_final=lote['precio_venta'],
            ))
    if detalles_articulo:
        DetalleArticulo.objects.bulk_create(detalles_articulo)

    # ── Crear avances ──
    avances = crear_avances(avances_data, cosechero)
    detalles_avance = [
        DetalleAvance(venta=venta, avance=avance, monto=avance.monto_pagado)
        for avance in avances
    ]
    if detalles_avance:
        DetalleAvance.objects.bulk_create(detalles_avance)

    # ── Recalcular total (una sola vez) ──
    venta.update_total()

    if imprimir:
        venta.impreso = True
        venta.save(update_fields=['impreso'])

    logger.info(
        f"Venta #{venta.id} procesada: cosechero={cosechero}, "
        f"artículos={len(items)}, avances={len(avances)}, total={venta.total}"
    )

    return {'success': True, 'venta': venta, 'errors': []}


# ─────────────────────────────────────────────
# Datos para tickets / detalles
# ─────────────────────────────────────────────

def procesar_detalles_articulos(detalles_articulos):
    """
    Agrupa detalles de artículos por (artículo, presentación, precio).
    Recibe un queryset de DetalleArticulo.
    Usada en ventas y en cosecheros/reportes.
    """
    articulos_procesados = [
        {
            'articulo_id': detalle.articulo.id,
            'descripcion': detalle.articulo.descripcion,
            'presentacion': detalle.articulo.presentacion,
            'cantidad': detalle.cantidad,
            'precio_venta_final': float(detalle.precio_venta_final),
            'importe': float(detalle.cantidad * detalle.precio_venta_final),
        }
        for detalle in detalles_articulos
    ]

    articulos_procesados.sort(
        key=lambda x: (x['articulo_id'], x['presentacion'], x['precio_venta_final'], x['descripcion'])
    )

    agrupados = []
    for key, group in groupby(
        articulos_procesados,
        key=lambda x: (x['articulo_id'], x['presentacion'], x['precio_venta_final'], x['descripcion']),
    ):
        group_list = list(group)
        agrupados.append({
            'descripcion': group_list[0]['descripcion'],
            'presentacion': group_list[0]['presentacion'],
            'cantidad_total': sum(item['cantidad'] for item in group_list),
            'precio_venta_final': key[2],
            'importe_total': sum(item['importe'] for item in group_list),
        })
    return agrupados


def obtener_detalles_venta(venta: Venta) -> dict:
    """Retorna los detalles agrupados de una venta para JSON response."""
    detalles_raw = DetalleArticulo.objects.filter(
        venta=venta
    ).select_related('articulo')

    # Agrupar por artículo + precio
    articulos_list = [
        {
            'articulo_id': d.articulo.id,
            'descripcion': d.articulo.descripcion,
            'presentacion': getattr(d.articulo, 'presentacion', ''),
            'cantidad': d.cantidad,
            'precio_venta_final': float(d.precio_venta_final),
            'importe': float(d.cantidad * d.precio_venta_final),
        }
        for d in detalles_raw
    ]

    articulos_list.sort(key=lambda x: (x['articulo_id'], x['precio_venta_final']))

    agrupados = []
    for key, group in groupby(articulos_list, key=lambda x: (x['articulo_id'], x['precio_venta_final'], x['descripcion'])):
        items = list(group)
        agrupados.append({
            'descripcion': items[0]['descripcion'],
            'presentacion': items[0]['presentacion'],
            'cantidad_total': sum(i['cantidad'] for i in items),
            'precio_venta_final': key[1],
            'importe_total': sum(i['importe'] for i in items),
        })

    # Avances
    avances = DetalleAvance.objects.filter(
        venta=venta
    ).select_related('avance')

    avances_list = [
        {
            'descripcion': a.avance.descripcion,
            'monto_pagado': float(a.avance.monto_pagado),
            'numero': a.avance.numero,
            'tipo': a.avance.tipo_avance,
        }
        for a in avances
    ]

    return {
        'cosechero_nombre': f"{venta.cosechero.nombre} {venta.cosechero.apellido}",
        'fecha_venta': venta.fecha_venta.strftime('%Y-%m-%d'),
        'total': float(venta.total),
        'detalles': agrupados,
        'avances': avances_list,
    }


def obtener_contexto_cosecha_default() -> dict:
    """Retorna cosecha más reciente y lista de cosechas."""
    cosechas = Cosecha.objects.all().order_by('-id')
    cosecha_default = cosechas.first()
    return {
        'cosechas': cosechas,
        'cosecha_default': cosecha_default,
    }

