from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import DecimalField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from articulo.models import Articulo
from proveedor.models import Proveedor

from .models import Compra, DetalleCompra


DOS_DECIMALES = Decimal('0.01')
MAXIMO_DECIMAL = Decimal('99999999.99')


class ProveedorCompraInvalido(Exception):
    pass


class CompraDuplicada(Exception):
    pass


class DetallesCompraInvalidos(Exception):
    def __init__(self, errores_por_linea):
        self.errores_por_linea = errores_por_linea
        super().__init__('El detalle de la compra contiene errores.')


@dataclass(frozen=True)
class DetalleCompraValidado:
    articulo: Articulo
    cantidad: Decimal
    precio_compra: Decimal
    precio_venta_sugerido: Decimal


def catalogo_articulos_por_proveedor(proveedor_id):
    ultimo_detalle = DetalleCompra.objects.filter(
        articulo_id=OuterRef('pk'),
        compra__is_active=True,
    ).order_by('-compra__fecha_compra', '-compra_id', '-id')

    campo_decimal = DecimalField(max_digits=10, decimal_places=2)
    return (
        Articulo.objects.filter(
            proveedor_id=proveedor_id,
            proveedor__is_active=True,
            is_active=True,
        )
        .annotate(
            inventario_restante=Coalesce(
                Sum(
                    'detallecompra__cantidad_restante',
                    filter=Q(
                        detallecompra__is_active=True,
                        detallecompra__compra__is_active=True,
                    ),
                ),
                Value(Decimal('0.00')),
                output_field=campo_decimal,
            ),
            ultimo_precio_compra=Subquery(
                ultimo_detalle.values('precio_compra')[:1],
                output_field=campo_decimal,
            ),
            ultimo_precio_venta=Subquery(
                ultimo_detalle.values('precio_venta_sugerido')[:1],
                output_field=campo_decimal,
            ),
        )
        .values(
            'id',
            'descripcion',
            'presentacion',
            'categoria',
            'cantidad_minima_orden',
            'inventario_restante',
            'ultimo_precio_compra',
            'ultimo_precio_venta',
        )
        .order_by('descripcion', 'id')
    )


def _entero_positivo(valor):
    if isinstance(valor, bool):
        return None
    try:
        entero = int(str(valor))
    except (TypeError, ValueError):
        return None
    return entero if entero > 0 and str(valor).strip() == str(entero) else None


def _decimal_positivo(valor, etiqueta):
    if isinstance(valor, bool) or valor in (None, ''):
        raise ValueError(f'{etiqueta} es obligatorio.')
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f'{etiqueta} debe ser un número válido.')

    if not numero.is_finite():
        raise ValueError(f'{etiqueta} debe ser un número válido.')
    if numero <= 0:
        raise ValueError(f'{etiqueta} debe ser mayor que cero.')
    if numero > MAXIMO_DECIMAL:
        raise ValueError(f'{etiqueta} excede el máximo permitido.')
    if numero.as_tuple().exponent < -2:
        raise ValueError(f'{etiqueta} admite como máximo dos decimales.')
    return numero.quantize(DOS_DECIMALES)


def validar_detalles_compra(proveedor, detalles, bloquear=False):
    if not isinstance(detalles, list) or not detalles:
        raise DetallesCompraInvalidos({})

    errores = {}
    ids_por_indice = {}
    ids_vistos = {}

    for indice, detalle in enumerate(detalles):
        errores_linea = []
        if not isinstance(detalle, dict):
            errores[indice] = ['La línea no tiene un formato válido.']
            continue

        articulo_id = _entero_positivo(detalle.get('articulo'))
        if articulo_id is None:
            errores_linea.append('Seleccione un artículo válido.')
        elif articulo_id in ids_vistos:
            errores_linea.append('El artículo está repetido en la compra.')
        else:
            ids_vistos[articulo_id] = indice
            ids_por_indice[indice] = articulo_id

        for campo, etiqueta in (
            ('cantidad', 'La cantidad'),
            ('precio_compra', 'El costo'),
            ('precio_venta_sugerido', 'El precio de venta'),
        ):
            try:
                _decimal_positivo(detalle.get(campo), etiqueta)
            except ValueError as error:
                errores_linea.append(str(error))

        if errores_linea:
            errores[indice] = errores_linea

    articulos = Articulo.objects.filter(
        pk__in=set(ids_por_indice.values()),
        proveedor=proveedor,
        is_active=True,
    )
    if bloquear:
        articulos = articulos.select_for_update()
    articulos_por_id = {articulo.pk: articulo for articulo in articulos}

    detalles_validados = []
    for indice, detalle in enumerate(detalles):
        articulo_id = ids_por_indice.get(indice)
        articulo = articulos_por_id.get(articulo_id)
        if articulo_id is not None and articulo is None:
            errores.setdefault(indice, []).append(
                'El artículo no está activo o no pertenece al proveedor seleccionado.'
            )
        if indice in errores or articulo is None:
            continue

        detalles_validados.append(DetalleCompraValidado(
            articulo=articulo,
            cantidad=_decimal_positivo(detalle.get('cantidad'), 'La cantidad'),
            precio_compra=_decimal_positivo(detalle.get('precio_compra'), 'El costo'),
            precio_venta_sugerido=_decimal_positivo(
                detalle.get('precio_venta_sugerido'),
                'El precio de venta',
            ),
        ))

    if errores:
        raise DetallesCompraInvalidos(errores)
    return detalles_validados


def registrar_compra(compra_form, proveedor_id, detalles):
    with transaction.atomic():
        proveedor = Proveedor.objects.select_for_update().filter(
            pk=proveedor_id,
            is_active=True,
        ).first()
        if proveedor is None:
            raise ProveedorCompraInvalido

        detalles_validados = validar_detalles_compra(
            proveedor,
            detalles,
            bloquear=True,
        )

        factura = compra_form.cleaned_data['factura']
        if Compra.objects.filter(proveedor=proveedor, factura=factura).exists():
            raise CompraDuplicada

        compra = compra_form.save(commit=False)
        compra.proveedor = proveedor
        try:
            compra.save()
        except IntegrityError as error:
            raise CompraDuplicada from error

        DetalleCompra.objects.bulk_create([
            DetalleCompra(
                compra=compra,
                articulo=detalle.articulo,
                cantidad=detalle.cantidad,
                cantidad_restante=detalle.cantidad,
                precio_compra=detalle.precio_compra,
                precio_venta_sugerido=detalle.precio_venta_sugerido,
                is_active=True,
            )
            for detalle in detalles_validados
        ])
        return compra
