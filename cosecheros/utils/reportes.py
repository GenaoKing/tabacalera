# app_tabacalera/utils/reportes.py
from decimal import Decimal
from django.db.models import Sum, Q
from cosecheros.models import (
    Cosecha, Cosechero, EntregaTabaco
)
from ventas.models import Venta, DetalleArticulo, DetalleAvance
# Importa tus helpers existentes
from cosecheros.views import procesar_detalles_articulos  # si está en views.py
from cosecheros.views import aplicar_tara                  # donde lo tengas definido

PRECIOS_VARIEDAD = {
    'Corojo Original': [12000, 12000, 9000, 4000, 3000, 3000, 2500],
    'Corojo 99': [12000, 12000, 9000, 4500, 3000, 3000, 2500],
    'Habano 92': [12000, 12000, 9000, 4500, 3000, 3000, 2500],
    'Criollo 98': [12000, 12000, 9000, 4500, 3000, 3000, 2500],
    'Piloto Mejorado': [12000, 12000, 9000, 4500, 3000, 3000, 2500],
    'HVA': [12000, 12000, 9000, 4500, 3000, 3000, 2500],
}

CLASIFICACIONES = (
    ('Centro Largo', 'centro_largo'),
    ('Centro Corto', 'centro_corto'),
    ('Uno y Medio',  'uno_medio'),
    ('Libre Pie',    'libre_pie'),
    ('Picadura',     'picadura'),
    ('Rezago',       'rezago'),
    ('Criollo',      'criollo'),
)

def _total_produccion_entregas(cosechero, cosecha) -> Decimal:
    """Calcula el total $ de producción (entregas) para un cosechero/cosecha
       usando exactamente la misma regla de precios + tara que en el PDF."""
    total = Decimal('0')
    entregas = EntregaTabaco.objects.filter(
        cosechero=cosechero, cosecha=cosecha
    ).order_by('fecha_entrega')

    for entrega in entregas:
        precios = PRECIOS_VARIEDAD.get(entrega.variedad)
        if not precios:
            # Si llega una variedad no contemplada, la saltamos o puedes lanzar excepción
            continue

        # Emparejamos precios con clasificaciones en orden
        for idx, (nombre_humano, attr) in enumerate(CLASIFICACIONES):
            cantidad = getattr(entrega, attr, 0) or 0
            if cantidad > 0:
                cantidad_tara = aplicar_tara(cantidad, nombre_humano)
                precio = Decimal(precios[idx])
                total += Decimal(cantidad_tara) * precio

    return total

def _total_gastos(cosechero, cosecha) -> Decimal:
    """Suma artículos + avances para cosechero/cosecha usando la misma
       lógica que tu PDF (procesar_detalles_articulos para artículos)."""
    ventas = Venta.objects.filter(cosechero_id=cosechero.id, cosecha=cosecha)

    # Artículos: reutiliza tu función para que coincidan importes
    detalles_articulos = (
        DetalleArticulo.objects
        .filter(venta__in=ventas)
        .select_related('articulo')
        .order_by('articulo__descripcion')
    )
    articulos_agrupados = procesar_detalles_articulos(detalles_articulos)
    subtotal_articulos = Decimal('0')
    for a in articulos_agrupados:
        # a['importe_total'] ya viene calculado como en el PDF
        subtotal_articulos += Decimal(str(a['importe_total']))

    # Avances
    subtotal_avances = (
        DetalleAvance.objects
        .filter(venta__in=ventas)
        .aggregate(s=Sum('avance__monto_pagado'))
        .get('s') or Decimal('0')
    )

    return (subtotal_articulos+subtotal_avances)

def calcular_saldos_cosecha(cosecha_id: int):
    """Devuelve lista de dicts con {cosechero, gastos, produccion, saldo}
       SOLO para cosecheros que tengan >= 1 entrega en esa cosecha."""
    cosecha = Cosecha.objects.get(pk=cosecha_id)

    # Cosecheros con al menos 1 entrega en la cosecha
    cosecheros = Cosechero.objects.filter(
        entregatabaco__cosecha=cosecha
    ).distinct()

    resultados = []
    for c in cosecheros:
        produccion = _total_produccion_entregas(c, cosecha)
        gastos = _total_gastos(c, cosecha)
        saldo = gastos - produccion  # positivo => nos debe
        resultados.append({
            "cosechero": c,
            "gastos": gastos,
            "produccion": produccion,
            "saldo": saldo,
        })

    # Filtrar sólo los que dan positivo
    resultados = [r for r in resultados if r["saldo"] < 0]
    return resultados
