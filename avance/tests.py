from datetime import date
from decimal import Decimal

from django.test import TestCase

from cosecheros.models import Cosecha, Cosechero
from ventas.models import Venta

from .services import import_confirmed_rows


class ImportacionAvancesCosechaTests(TestCase):
    def test_no_reutiliza_venta_de_otra_cosecha(self):
        cosechero = Cosechero.objects.create(
            nombre='Importado', apellido='Prueba', cedula='', numero_cuenta_banco=None,
            direccion='Local', telefono='', terreno_sembrado=Decimal('1.00'),
        )
        anterior = Cosecha.objects.create(
            nombre='Anterior', fecha_inicio=date(2025, 1, 1), fecha_fin=date(2025, 12, 31),
        )
        actual = Cosecha.objects.create(
            nombre='Actual', fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31),
        )
        Venta.objects.create(
            cosechero=cosechero, cosecha=anterior,
            fecha_venta=date(2026, 8, 8), total=Decimal('10.00'),
        )
        filas = [{
            'index': 1, 'cosechero_id': cosechero.id, 'monto': '25.00',
            'fecha': '2026-08-04', 'tipo_avance': 'efectivo',
            'numero': 'IMP-1', 'descripcion': 'Importación segura',
        }]

        resultado = import_confirmed_rows(filas, actual.id, 'Avance importado')

        self.assertEqual(resultado['errores'], [])
        self.assertEqual(Venta.objects.filter(cosecha=anterior).count(), 1)
        venta_actual = Venta.objects.get(cosecha=actual)
        self.assertEqual(venta_actual.cosechero, cosechero)
        self.assertEqual(venta_actual.fecha_venta, date(2026, 8, 8))
        self.assertEqual(venta_actual.detalle_avances.get().monto, Decimal('25.00'))

        venta_actual.impreso = True
        venta_actual.save(update_fields=['impreso'])
        filas[0]['numero'] = 'IMP-2'
        filas[0]['monto'] = '5.00'
        segundo = import_confirmed_rows(filas, actual.id, 'Avance importado')
        venta_actual.refresh_from_db()
        self.assertEqual(segundo['ventas_actualizadas'], 1)
        self.assertFalse(venta_actual.impreso)
        self.assertEqual(venta_actual.detalle_avances.count(), 2)
