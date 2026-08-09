"""
ventas/services.py
──────────────────
Capa de servicios para el módulo de ventas.
Toda la lógica de negocio vive aquí, las views solo orquestan HTTP.
"""
import decimal
import hashlib
import json
import logging
import uuid
from datetime import date
from decimal import Decimal
from itertools import groupby
from typing import Optional

from django.db import connection, transaction
from django.db.models import Sum

from app.business_dates import proximo_sabado
from articulo.models import Articulo
from avance.models import Avance
from compra.models import DetalleCompra
from cosecheros.models import Cosechero, Cosecha

from .models import Venta, DetalleArticulo, DetalleAvance, OperacionVenta

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Utilidades de fecha (sábado = cierre semanal)
# ─────────────────────────────────────────────

def obtener_venta_existente(
    cosechero_id: int,
    cosecha_id: int,
    fecha_sabado: date,
) -> Optional[Venta]:
    """Busca la cuenta semanal exacta y detecta historia ambigua."""
    ventas = Venta.objects.filter(
        cosechero_id=cosechero_id,
        cosecha_id=cosecha_id,
        fecha_venta=fecha_sabado,
        is_active=True,
    ).order_by('id')
    if ventas.count() > 1:
        raise ValueError(
            'Esta semana tiene más de un ticket histórico activo. '
            'No se agregarán movimientos automáticamente.'
        )
    return ventas.first()


# ─────────────────────────────────────────────
# Inventario y precios (FIFO por lotes)
# ─────────────────────────────────────────────

def calcular_inventario_articulo(articulo_id: int, bloquear: bool = False) -> Decimal:
    """Retorna el inventario total disponible para un artículo."""
    lotes = DetalleCompra.objects.filter(
        articulo_id=articulo_id,
        cantidad_restante__gt=0,
        compra__is_active=True,
        is_active=True,
    ).order_by('pk')
    if bloquear:
        lotes = lotes.select_for_update()
        return sum((lote.cantidad_restante for lote in lotes), Decimal('0'))
    return lotes.aggregate(total=Sum('cantidad_restante'))['total'] or Decimal('0')


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

def validar_inventario_suficiente(items: list[dict], bloquear: bool = False) -> list[str]:
    """
    Recibe lista de {'articulo_id': int, 'cantidad': Decimal}.
    Retorna lista de errores (vacía si todo OK).
    """
    errores = []
    for item in items:
        inv = calcular_inventario_articulo(item['articulo_id'], bloquear=bloquear)
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

        try:
            monto_decimal = Decimal(monto)
        except (decimal.InvalidOperation, ValueError):
            errores.append(f"Avance #{i + 1}: monto inválido.")
            continue
        if monto_decimal <= 0:
            errores.append(f"Avance #{i + 1}: el monto debe ser mayor que cero.")
            continue

        avances_data.append({
            'descripcion': descripcion or f"Avance {tipo_avance} #{numero}",
            'tipo_avance': tipo_avance,
            'numero': numero,
            'monto_pagado': monto_decimal,
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
    cantidades = {}

    for i in range(total):
        articulo_id = post_data.get(f'detalle_articulos-{i}-articulo')
        cantidad = post_data.get(f'detalle_articulos-{i}-cantidad')

        if articulo_id and cantidad:
            try:
                cantidad_decimal = Decimal(str(cantidad))
                articulo_entero = int(articulo_id)
            except (decimal.InvalidOperation, TypeError, ValueError):
                continue
            cantidades[articulo_entero] = (
                cantidades.get(articulo_entero, Decimal('0')) + cantidad_decimal
            )

    return [
        {'articulo_id': articulo_id, 'cantidad': cantidad}
        for articulo_id, cantidad in sorted(cantidades.items())
    ]


def _huella_operacion(
    cosechero_id: int,
    cosecha_id: int,
    fecha_movimiento: date,
    items: list[dict],
    avances: list[dict],
    imprimir: bool,
) -> str:
    payload = {
        'cosechero_id': cosechero_id,
        'cosecha_id': cosecha_id,
        'fecha_movimiento': fecha_movimiento.isoformat(),
        'items': [
            {'articulo_id': i['articulo_id'], 'cantidad': str(i['cantidad'])}
            for i in items
        ],
        'avances': [
            {
                key: str(value) if isinstance(value, Decimal) else value
                for key, value in avance.items()
            }
            for avance in avances
        ],
        'imprimir': imprimir,
    }
    serializado = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(serializado.encode('utf-8')).hexdigest()


def _adquirir_bloqueo_semana(cosechero_id: int, cosecha_id: int, fecha_sabado: date):
    """Serializa altas sobre una misma cuenta semanal en SQL Server."""
    if connection.vendor != 'microsoft':
        return
    recurso = f'venta-semanal:{cosechero_id}:{cosecha_id}:{fecha_sabado.isoformat()}'
    with connection.cursor() as cursor:
        cursor.execute(
            """
            DECLARE @resultado int;
            EXEC @resultado = sp_getapplock
                @Resource = %s,
                @LockMode = 'Exclusive',
                @LockOwner = 'Transaction',
                @LockTimeout = 10000;
            SELECT @resultado;
            """,
            [recurso],
        )
        resultado = cursor.fetchone()[0]
    if resultado < 0:
        raise TimeoutError('No se pudo bloquear la cuenta semanal. Intente nuevamente.')


@transaction.atomic
def procesar_venta(
    post_data: dict,
    imprimir: bool = False,
    idempotency_key=None,
    usuario=None,
) -> dict:
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
    try:
        cosechero_id = int(post_data.get('cosechero', 0))
        cosecha_id = int(post_data.get('cosecha', 0))
    except (TypeError, ValueError):
        return {'success': False, 'venta': None, 'errors': ['Datos incompletos']}
    fecha_raw = post_data.get('fecha_venta', '')

    if not all([cosechero_id, cosecha_id, fecha_raw]):
        return {'success': False, 'venta': None, 'errors': ['Datos incompletos']}

    try:
        cosechero = Cosechero.objects.get(id=cosechero_id, is_active=True)
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

    if any(item['cantidad'] <= 0 for item in items):
        return {
            'success': False, 'venta': None,
            'errors': ['Las cantidades de artículos deben ser mayores que cero.'],
        }

    if items:
        errores_inv = validar_inventario_suficiente(items)
        if errores_inv:
            return {'success': False, 'venta': None, 'errors': errores_inv}

    # ── Extraer y validar avances (antes de tocar la BD) ──
    avances_data, errores_avance = extraer_avances_validados(post_data)
    if errores_avance:
        return {'success': False, 'venta': None, 'errors': errores_avance}

    if not items and not avances_data:
        return {
            'success': False, 'venta': None,
            'errors': ['Agregue al menos un artículo o un avance.'],
        }

    try:
        clave = uuid.UUID(str(idempotency_key)) if idempotency_key else uuid.uuid4()
    except (TypeError, ValueError, AttributeError):
        return {'success': False, 'venta': None, 'errors': ['Clave de operación inválida.']}

    huella = _huella_operacion(
        cosechero_id, cosecha_id, fecha_venta, items, avances_data, imprimir,
    )
    operacion_existente = OperacionVenta.objects.filter(clave=clave).select_related('venta').first()
    if operacion_existente:
        if operacion_existente.huella_payload != huella:
            return {
                'success': False, 'venta': operacion_existente.venta,
                'errors': ['La clave de operación ya fue usada con datos diferentes.'],
                'idempotency_conflict': True,
            }
        return {
            'success': True, 'venta': operacion_existente.venta, 'errors': [],
            'operacion': operacion_existente, 'replayed': True,
        }

    _adquirir_bloqueo_semana(cosechero_id, cosecha_id, fecha_sabado)

    # Revalidar tras adquirir el bloqueo: otra solicitud pudo terminar mientras esperábamos.
    operacion_existente = OperacionVenta.objects.filter(clave=clave).select_related('venta').first()
    if operacion_existente:
        if operacion_existente.huella_payload != huella:
            return {
                'success': False, 'venta': operacion_existente.venta,
                'errors': ['La clave de operación ya fue usada con datos diferentes.'],
                'idempotency_conflict': True,
            }
        return {
            'success': True, 'venta': operacion_existente.venta, 'errors': [],
            'operacion': operacion_existente, 'replayed': True,
        }

    # Bloquear los lotes en orden estable y revalidar tras cualquier espera.
    if items:
        errores_inv = validar_inventario_suficiente(items, bloquear=True)
        if errores_inv:
            return {'success': False, 'venta': None, 'errors': errores_inv}

    # ── Obtener o crear venta ──
    try:
        venta_existente = obtener_venta_existente(cosechero_id, cosecha_id, fecha_sabado)
    except ValueError as exc:
        return {'success': False, 'venta': None, 'errors': [str(exc)]}

    if venta_existente:
        venta = venta_existente
    else:
        venta = Venta.objects.create(
            cosechero=cosechero,
            cosecha=cosecha,
            fecha_venta=fecha_sabado,
            total=Decimal('0'),
            impreso=False,
        )

    operacion = OperacionVenta.objects.create(
        clave=clave,
        venta=venta,
        usuario=usuario if getattr(usuario, 'is_authenticated', False) else None,
        fecha_movimiento=fecha_venta,
        huella_payload=huella,
        total_movimiento=Decimal('0'),
        impresion_solicitada=imprimir,
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
                operacion=operacion,
                articulo_id=item['articulo_id'],
                cantidad=lote['cantidad'],
                precio_venta_final=lote['precio_venta'],
            ))
    if detalles_articulo:
        DetalleArticulo.objects.bulk_create(detalles_articulo)

    # ── Crear avances ──
    avances = crear_avances(avances_data, cosechero)
    detalles_avance = [
        DetalleAvance(
            venta=venta, operacion=operacion,
            avance=avance, monto=avance.monto_pagado,
        )
        for avance in avances
    ]
    if detalles_avance:
        DetalleAvance.objects.bulk_create(detalles_avance)

    # ── Recalcular total (una sola vez) ──
    venta.update_total()
    total_articulos_operacion = sum(
        (d.cantidad * d.precio_venta_final for d in detalles_articulo),
        Decimal('0'),
    )
    total_avances_operacion = sum(
        (d.monto for d in detalles_avance), Decimal('0'),
    )
    operacion.total_movimiento = total_articulos_operacion + total_avances_operacion
    operacion.save(update_fields=['total_movimiento'])

    if venta.impreso:
        venta.impreso = False
        venta.save(update_fields=['impreso'])

    logger.info(
        f"Venta #{venta.id} procesada: cosechero={cosechero}, "
        f"artículos={len(items)}, avances={len(avances)}, total={venta.total}"
    )

    return {
        'success': True, 'venta': venta, 'errors': [],
        'operacion': operacion, 'replayed': False,
    }


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
            'precio_venta_final': detalle.precio_venta_final,
            'importe': detalle.cantidad * detalle.precio_venta_final,
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
            'cantidad_total': sum((item['cantidad'] for item in group_list), Decimal('0')),
            'precio_venta_final': key[2],
            'importe_total': sum((item['importe'] for item in group_list), Decimal('0')),
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
            'precio_venta_final': d.precio_venta_final,
            'importe': d.cantidad * d.precio_venta_final,
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
            'cantidad_total': sum((i['cantidad'] for i in items), Decimal('0')),
            'precio_venta_final': key[1],
            'importe_total': sum((i['importe'] for i in items), Decimal('0')),
        })

    # Avances
    avances = DetalleAvance.objects.filter(
        venta=venta
    ).select_related('avance')

    avances_list = [
        {
            'descripcion': a.avance.descripcion,
            'monto_pagado': a.monto,
            'numero': a.avance.numero,
            'tipo': a.avance.tipo_avance,
        }
        for a in avances
    ]

    return {
        'cosechero_nombre': f"{venta.cosechero.nombre} {venta.cosechero.apellido}",
        'fecha_venta': venta.fecha_venta.strftime('%Y-%m-%d'),
        'total': venta.total,
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

