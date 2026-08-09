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
from datetime import date
from decimal import Decimal
from typing import Iterable

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


def calcular_quintales_entrega(entrega: EntregaTabaco) -> Decimal:
    """Suma la cantidad entregada usando el mismo ajuste de tara del reporte."""
    total = Decimal('0')
    for _, campo_entrega, _, multiplicador in CLASIFICACIONES:
        cantidad = getattr(entrega, campo_entrega) or Decimal('0')
        if cantidad > 0:
            total += aplicar_tara(cantidad, multiplicador)
    return total


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
    """Suma artículos + avances desde la misma fuente de conciliación."""
    filas = calcular_resumenes_cosecha(cosecha.id, cosechero_ids=[cosechero.id])
    return filas[0]['gastos'] if filas else Decimal('0')


ACTIVIDAD_ETIQUETAS = {
    'entrega': 'Entrega de tabaco',
    'avance': 'Avance',
    'articulo': 'Artículo',
    'venta': 'Venta semanal',
}
ACTIVIDAD_ORDEN = tuple(ACTIVIDAD_ETIQUETAS)


def _agregar_actividad(
    actividades: dict[int, list[tuple[date, str, str]]],
    cosechero_id: int,
    fecha: date | None,
    tipo: str,
    precision: str,
) -> None:
    if fecha is not None:
        actividades.setdefault(cosechero_id, []).append((fecha, tipo, precision))


def _ultima_actividad(candidatas: list[tuple[date, str, str]]) -> dict:
    if not candidatas:
        return {
            'ultima_actividad_fecha': None,
            'ultima_actividad_tipos': (),
            'ultima_actividad_etiqueta': 'Sin actividad fechada',
            'ultima_actividad_precision': None,
        }

    fecha_maxima = max(fecha for fecha, _, _ in candidatas)
    candidatas_maximas = [fila for fila in candidatas if fila[0] == fecha_maxima]
    tipos_presentes = {tipo for _, tipo, _ in candidatas_maximas}
    tipos = tuple(tipo for tipo in ACTIVIDAD_ORDEN if tipo in tipos_presentes)
    precisiones = {precision for _, _, precision in candidatas_maximas}
    if len(precisiones) > 1:
        precision = 'mixta'
    else:
        precision = precisiones.pop()
    return {
        'ultima_actividad_fecha': fecha_maxima,
        'ultima_actividad_tipos': tipos,
        'ultima_actividad_etiqueta': ' + '.join(ACTIVIDAD_ETIQUETAS[tipo] for tipo in tipos),
        'ultima_actividad_precision': precision,
    }


def calcular_resumenes_cosecha(
    cosecha_id: int,
    cosechero_ids: Iterable[int] | None = None,
) -> list[dict]:
    """Construye el universo financiero completo de una cosecha.

    La unión incluye cosecheros con entregas o ventas activas. Los avances
    únicamente pertenecen a una cosecha cuando están vinculados a una Venta.
    Todos los importes permanecen como Decimal hasta su serialización.
    """
    from ventas.models import DetalleArticulo, DetalleAvance, Venta

    filtro_ids = None if cosechero_ids is None else {int(pk) for pk in cosechero_ids}
    if filtro_ids == set():
        return []

    cosecha = Cosecha.objects.get(pk=cosecha_id)
    precios = obtener_precios(cosecha)

    ventas_qs = Venta.objects.filter(cosecha=cosecha, is_active=True).select_related('cosechero')
    entregas_qs = EntregaTabaco.objects.filter(cosecha=cosecha).select_related('cosechero')
    if filtro_ids is not None:
        ventas_qs = ventas_qs.filter(cosechero_id__in=filtro_ids)
        entregas_qs = entregas_qs.filter(cosechero_id__in=filtro_ids)

    ventas = list(ventas_qs.order_by('id'))
    entregas = list(entregas_qs.order_by('cosechero_id', 'fecha_entrega', 'id'))
    venta_ids = [venta.id for venta in ventas]

    cosecheros: dict[int, Cosechero] = {}
    gastos_articulos: dict[int, Decimal] = {}
    gastos_avances: dict[int, Decimal] = {}
    produccion: dict[int, Decimal] = {}
    quintales_producidos: dict[int, Decimal] = {}
    cantidad_entregas: dict[int, int] = {}
    entregas_sin_precio: dict[int, int] = {}
    actividades: dict[int, list[tuple[date, str, str]]] = {}

    for venta in ventas:
        cosecheros[venta.cosechero_id] = venta.cosechero

    for entrega in entregas:
        cosechero_id = entrega.cosechero_id
        cosecheros[cosechero_id] = entrega.cosechero
        cantidad_entregas[cosechero_id] = cantidad_entregas.get(cosechero_id, 0) + 1
        resultado = calcular_produccion_entrega(entrega, precios.get(entrega.variedad))
        produccion[cosechero_id] = (
            produccion.get(cosechero_id, Decimal('0')) + resultado['subtotal']
        )
        quintales_producidos[cosechero_id] = (
            quintales_producidos.get(cosechero_id, Decimal('0'))
            + calcular_quintales_entrega(entrega)
        )
        if resultado['sin_precio']:
            entregas_sin_precio[cosechero_id] = entregas_sin_precio.get(cosechero_id, 0) + 1
        _agregar_actividad(actividades, cosechero_id, entrega.fecha_entrega, 'entrega', 'exacta')

    ventas_con_detalle: set[int] = set()
    if venta_ids:
        detalles_articulo = DetalleArticulo.objects.filter(venta_id__in=venta_ids).values(
            'venta_id', 'venta__cosechero_id', 'venta__fecha_venta',
            'cantidad', 'precio_venta_final', 'operacion__fecha_movimiento',
        )
        for detalle in detalles_articulo:
            venta_id = detalle['venta_id']
            cosechero_id = detalle['venta__cosechero_id']
            ventas_con_detalle.add(venta_id)
            importe = detalle['cantidad'] * detalle['precio_venta_final']
            gastos_articulos[cosechero_id] = (
                gastos_articulos.get(cosechero_id, Decimal('0')) + importe
            )
            fecha_operacion = detalle['operacion__fecha_movimiento']
            _agregar_actividad(
                actividades,
                cosechero_id,
                fecha_operacion or detalle['venta__fecha_venta'],
                'articulo',
                'exacta' if fecha_operacion else 'cierre_semanal',
            )

        detalles_avance = DetalleAvance.objects.filter(venta_id__in=venta_ids).values(
            'venta_id', 'venta__cosechero_id', 'monto', 'avance__fecha',
        )
        for detalle in detalles_avance:
            venta_id = detalle['venta_id']
            cosechero_id = detalle['venta__cosechero_id']
            ventas_con_detalle.add(venta_id)
            gastos_avances[cosechero_id] = (
                gastos_avances.get(cosechero_id, Decimal('0')) + detalle['monto']
            )
            _agregar_actividad(
                actividades, cosechero_id, detalle['avance__fecha'], 'avance', 'exacta',
            )

    for venta in ventas:
        if venta.id not in ventas_con_detalle:
            _agregar_actividad(
                actividades, venta.cosechero_id, venta.fecha_venta,
                'venta', 'cierre_semanal',
            )

    resultados = []
    for cosechero_id, cosechero in cosecheros.items():
        articulos = gastos_articulos.get(cosechero_id, Decimal('0'))
        avances = gastos_avances.get(cosechero_id, Decimal('0'))
        gastos = articulos + avances
        total_produccion = produccion.get(cosechero_id, Decimal('0'))
        total_quintales = quintales_producidos.get(cosechero_id, Decimal('0'))
        numero_entregas = cantidad_entregas.get(cosechero_id, 0)
        tareas = cosechero.terreno_sembrado
        fila = {
            'cosechero': cosechero,
            'gastos_articulos': articulos,
            'gastos_avances': avances,
            'gastos': gastos,
            'produccion': total_produccion,
            'saldo': gastos - total_produccion,
            'tareas_sembradas': tareas,
            'gasto_promedio_tarea': gastos / tareas if tareas > 0 else None,
            'produccion_promedio_tarea': total_produccion / tareas if tareas > 0 else None,
            'quintales_producidos': total_quintales,
            'quintales_promedio_tarea': total_quintales / tareas if tareas > 0 else None,
            'cantidad_entregas': numero_entregas,
            'sin_produccion_entregada': gastos > 0 and numero_entregas == 0,
            'entregas_sin_precio': entregas_sin_precio.get(cosechero_id, 0),
        }
        fila.update(_ultima_actividad(actividades.get(cosechero_id, [])))
        resultados.append(fila)

    return sorted(
        resultados,
        key=lambda fila: (
            fila['cosechero'].nombre.lower(),
            fila['cosechero'].apellido.lower(),
            fila['cosechero'].id,
        ),
    )


def calcular_saldos_cosecha(cosecha_id: int) -> list[dict]:
    """
    Alias compatible del universo financiero completo de la cosecha.
    saldo = gastos - produccion (positivo => el cosechero nos debe;
    negativo => se le debe).

    No filtra por signo: el llamador agrupa o muestra ambos lados.
    """
    return calcular_resumenes_cosecha(cosecha_id)


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
