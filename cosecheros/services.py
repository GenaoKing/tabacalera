"""
cosecheros/services.py
───────────────────────
Lógica de negocio para el reporte de cosechero: cálculo de producción
(entregas de tabaco valoradas por precio de variedad/cosecha + tara),
gastos (artículos + avances) y saldo resultante.

Única fuente de verdad para estos cálculos — reemplaza la tabla de
precios hardcodeada y duplicada que antes vivía en views.py y en
utils/reportes.py.
"""
from decimal import Decimal

from django.db.models import Sum

from .models import Cosecha, Cosechero, EntregaTabaco, PrecioVariedadCosecha

# (etiqueta, campo en EntregaTabaco, campo en PrecioVariedadCosecha, multiplicador de tara)
CLASIFICACIONES = [
    ('Centro Largo', 'centro_largo', 'precio_centro_largo', Decimal('1.80')),
    ('Centro Corto', 'centro_corto', 'precio_centro_corto', Decimal('1.80')),
    ('Uno y Medio', 'uno_medio', 'precio_uno_medio', Decimal('1.80')),
    ('Libre Pie', 'libre_pie', 'precio_libre_pie', Decimal('1.80')),
    ('Picadura', 'picadura', 'precio_picadura', Decimal('1.60')),
    ('Rezago', 'rezago', 'precio_rezago', Decimal('1.60')),
    ('Criollo', 'criollo', 'precio_criollo', Decimal('1.60')),
]


def aplicar_tara(cantidad: Decimal, multiplicador: Decimal) -> Decimal:
    """
    Aplica el descuento de tara: la parte entera de la cantidad se
    mantiene igual, la parte decimal se multiplica por el factor de tara
    de la clasificación (1.80 para hojas de capa, 1.60 para las demás).
    """
    cantidad = Decimal(cantidad)
    parte_entera = int(cantidad)
    parte_decimal = cantidad - parte_entera
    return parte_entera + parte_decimal * multiplicador


def obtener_precios(cosecha: Cosecha) -> dict[str, PrecioVariedadCosecha]:
    """Retorna {variedad: PrecioVariedadCosecha} para la cosecha, en una sola query."""
    return {
        precio.variedad: precio
        for precio in PrecioVariedadCosecha.objects.filter(cosecha=cosecha)
    }


def calcular_produccion_entrega(entrega: EntregaTabaco, precio_variedad: PrecioVariedadCosecha | None) -> dict:
    """
    Calcula el valor $ de una entrega de tabaco, clasificación por
    clasificación, aplicando tara y el precio vigente para su cosecha.

    Retorna {'lineas': [...], 'subtotal': Decimal, 'sin_precio': bool}.
    'sin_precio' es True si la variedad no tiene precio cargado para esa
    cosecha (evita KeyError; el llamador decide cómo advertir de esto).
    """
    lineas = []
    subtotal = Decimal('0')

    if precio_variedad is None:
        return {'lineas': lineas, 'subtotal': subtotal, 'sin_precio': True}

    for nombre_humano, campo_entrega, campo_precio, multiplicador in CLASIFICACIONES:
        cantidad = getattr(entrega, campo_entrega, None) or Decimal('0')
        if cantidad > 0:
            cantidad_tara = aplicar_tara(cantidad, multiplicador)
            precio = getattr(precio_variedad, campo_precio)
            importe = cantidad_tara * precio
            subtotal += importe
            lineas.append({
                'clasificacion': nombre_humano,
                'cantidad_tara': cantidad_tara,
                'precio': precio,
                'importe': importe,
            })

    return {'lineas': lineas, 'subtotal': subtotal, 'sin_precio': False}


def calcular_produccion_total(cosechero: Cosechero, cosecha: Cosecha) -> Decimal:
    """Total $ de producción (entregas) de un cosechero en una cosecha."""
    precios = obtener_precios(cosecha)
    total = Decimal('0')
    entregas = EntregaTabaco.objects.filter(cosechero=cosechero, cosecha=cosecha)
    for entrega in entregas:
        resultado = calcular_produccion_entrega(entrega, precios.get(entrega.variedad))
        total += resultado['subtotal']
    return total


def calcular_gastos(cosechero: Cosechero, cosecha: Cosecha) -> Decimal:
    """Suma artículos + avances para cosechero/cosecha (gastos a cuenta de la cosecha)."""
    # Import local para evitar dependencia circular a nivel de módulo con ventas.
    from ventas.models import DetalleArticulo, DetalleAvance, Venta
    from ventas.services import procesar_detalles_articulos

    ventas = Venta.objects.filter(cosechero_id=cosechero.id, cosecha=cosecha)

    detalles_articulos = (
        DetalleArticulo.objects
        .filter(venta__in=ventas)
        .select_related('articulo')
        .order_by('articulo__descripcion')
    )
    articulos_agrupados = procesar_detalles_articulos(detalles_articulos)
    subtotal_articulos = sum(
        (Decimal(str(a['importe_total'])) for a in articulos_agrupados), Decimal('0')
    )

    subtotal_avances = (
        DetalleAvance.objects
        .filter(venta__in=ventas)
        .aggregate(s=Sum('avance__monto_pagado'))
        .get('s') or Decimal('0')
    )

    return subtotal_articulos + subtotal_avances


def calcular_saldos_cosecha(cosecha_id: int) -> list[dict]:
    """
    Retorna [{cosechero, gastos, produccion, saldo}] para todos los
    cosecheros con al menos una entrega en la cosecha. saldo = gastos -
    produccion (positivo => el cosechero nos debe; negativo => se le debe).

    No filtra por signo: el llamador decide cómo agrupar/mostrar ambos
    lados (ver comando resumen_perdidas_cosecha).
    """
    cosecha = Cosecha.objects.get(pk=cosecha_id)

    cosecheros = Cosechero.objects.filter(
        entregatabaco__cosecha=cosecha
    ).distinct()

    resultados = []
    for cosechero in cosecheros:
        produccion = calcular_produccion_total(cosechero, cosecha)
        gastos = calcular_gastos(cosechero, cosecha)
        resultados.append({
            'cosechero': cosechero,
            'gastos': gastos,
            'produccion': produccion,
            'saldo': gastos - produccion,
        })
    return resultados


def clonar_precios(desde_cosecha: Cosecha, hacia_cosecha: Cosecha) -> int:
    """
    Copia los precios de una cosecha a otra (p.ej. al abrir una cosecha
    nueva). No sobreescribe precios que 'hacia_cosecha' ya tenga.
    Retorna la cantidad de filas creadas.
    """
    creadas = 0
    for precio in PrecioVariedadCosecha.objects.filter(cosecha=desde_cosecha):
        _, created = PrecioVariedadCosecha.objects.get_or_create(
            cosecha=hacia_cosecha,
            variedad=precio.variedad,
            defaults={
                'precio_centro_largo': precio.precio_centro_largo,
                'precio_centro_corto': precio.precio_centro_corto,
                'precio_uno_medio': precio.precio_uno_medio,
                'precio_libre_pie': precio.precio_libre_pie,
                'precio_picadura': precio.precio_picadura,
                'precio_rezago': precio.precio_rezago,
                'precio_criollo': precio.precio_criollo,
            },
        )
        if created:
            creadas += 1
    return creadas


def cosecha_mas_reciente_con_precios(excluir: Cosecha | None = None) -> Cosecha | None:
    """Última cosecha (por fecha_inicio) que ya tiene al menos un precio cargado."""
    qs = Cosecha.objects.filter(precios__isnull=False).distinct().order_by('-fecha_inicio')
    if excluir is not None:
        qs = qs.exclude(pk=excluir.pk)
    return qs.first()
