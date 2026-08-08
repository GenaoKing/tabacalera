import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier

from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from unittest.mock import patch

from articulo.models import Articulo
from compra.models import Compra, DetalleCompra
from cosecheros.models import Cosecha, Cosechero
from proveedor.models import Proveedor

from .models import DetalleArticulo, OperacionVenta, Venta
from .services import procesar_venta


class VentaSeguraTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user('operador', password='prueba')
        cls.cosechero = Cosechero.objects.create(
            nombre='Prueba', apellido='Semanal', cedula='', numero_cuenta_banco=None,
            direccion='Local', telefono='', terreno_sembrado=Decimal('1.00'),
        )
        cls.cosecha = Cosecha.objects.create(
            nombre='Prueba 2026', fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31),
        )
        proveedor = Proveedor.objects.create(
            nombre='Proveedor prueba', direccion='Local', telefono='000',
            correo_electronico='prueba@example.com',
        )
        cls.articulo = Articulo.objects.create(
            descripcion='Producto decimal', categoria='abonos', presentacion='unidad',
            cantidad_minima_orden=1, proveedor=proveedor,
        )
        compra = Compra.objects.create(
            proveedor=proveedor, fecha_compra=date(2026, 1, 1),
            fecha_vencimiento=date(2027, 1, 1), factura='TEST-1', NFC='TEST-NFC',
        )
        cls.lote = DetalleCompra.objects.create(
            compra=compra, articulo=cls.articulo, cantidad=Decimal('10.00'),
            cantidad_restante=Decimal('10.00'), precio_compra=Decimal('50.00'),
            precio_venta_sugerido=Decimal('75.00'),
        )

    def payload(self, cantidad='0.50'):
        return {
            'cosechero': str(self.cosechero.id),
            'cosecha': str(self.cosecha.id),
            'fecha_venta': '2026-08-04',
            'detalle_articulos-TOTAL_FORMS': '1',
            'detalle_articulos-0-articulo': str(self.articulo.id),
            'detalle_articulos-0-cantidad': cantidad,
            'detalle_avances-TOTAL_FORMS': '0',
        }

    def setUp(self):
        self.client.force_login(self.usuario)

    def test_reintento_idempotente_conserva_decimal_y_fifo(self):
        clave = uuid.uuid4()
        primero = procesar_venta(self.payload(), idempotency_key=clave, usuario=self.usuario)
        segundo = procesar_venta(self.payload(), idempotency_key=clave, usuario=self.usuario)

        self.assertTrue(primero['success'])
        self.assertTrue(segundo['success'])
        self.assertTrue(segundo['replayed'])
        self.assertEqual(OperacionVenta.objects.count(), 1)
        self.assertEqual(DetalleArticulo.objects.count(), 1)
        self.assertEqual(DetalleArticulo.objects.get().cantidad, Decimal('0.50'))
        self.lote.refresh_from_db()
        self.assertEqual(self.lote.cantidad_restante, Decimal('9.50'))

    def test_misma_clave_con_payload_distinto_devuelve_conflicto(self):
        clave = uuid.uuid4()
        procesar_venta(self.payload(), idempotency_key=clave, usuario=self.usuario)
        resultado = procesar_venta(self.payload('1.00'), idempotency_key=clave, usuario=self.usuario)
        self.assertFalse(resultado['success'])
        self.assertTrue(resultado['idempotency_conflict'])
        self.assertEqual(OperacionVenta.objects.count(), 1)

    def test_operaciones_de_la_semana_reutilizan_venta_y_marcan_pendiente(self):
        primero = procesar_venta(self.payload(), idempotency_key=uuid.uuid4(), usuario=self.usuario)
        venta = primero['venta']
        venta.impreso = True
        venta.save(update_fields=['impreso'])

        segundo = procesar_venta(self.payload('1.00'), idempotency_key=uuid.uuid4(), usuario=self.usuario)
        venta.refresh_from_db()
        self.assertEqual(segundo['venta'].id, venta.id)
        self.assertEqual(Venta.objects.count(), 1)
        self.assertFalse(venta.impreso)

    def test_semana_historica_ambigua_no_se_modifica(self):
        sabado = date(2026, 8, 8)
        Venta.objects.create(
            cosechero=self.cosechero, cosecha=self.cosecha,
            fecha_venta=sabado, total=Decimal('0'),
        )
        Venta.objects.create(
            cosechero=self.cosechero, cosecha=self.cosecha,
            fecha_venta=sabado, total=Decimal('0'),
        )
        resultado = procesar_venta(self.payload(), idempotency_key=uuid.uuid4(), usuario=self.usuario)
        self.assertFalse(resultado['success'])
        self.assertIn('más de un ticket', resultado['errors'][0])
        self.assertEqual(OperacionVenta.objects.count(), 0)

    def test_api_repite_sin_duplicar_y_conflicto_responde_409(self):
        clave = str(uuid.uuid4())
        headers = {
            'HTTP_IDEMPOTENCY_KEY': clave,
            'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest',
            'HTTP_ACCEPT': 'application/json',
        }
        primero = self.client.post(reverse('ventas'), self.payload(), **headers)
        replay = self.client.post(reverse('ventas'), self.payload(), **headers)
        conflicto = self.client.post(reverse('ventas'), self.payload('1.00'), **headers)

        self.assertEqual(primero.status_code, 200)
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()['replayed'])
        self.assertEqual(conflicto.status_code, 409)
        self.assertEqual(OperacionVenta.objects.count(), 1)

    def test_impresion_solo_post_y_falla_no_revierte_venta(self):
        resultado = procesar_venta(self.payload(), idempotency_key=uuid.uuid4(), usuario=self.usuario)
        venta = resultado['venta']
        self.assertEqual(self.client.get(reverse('view_imprimir', args=[venta.id])).status_code, 405)
        with patch('ventas.views._imprimir_ticket', return_value=False):
            respuesta = self.client.post(reverse('view_imprimir', args=[venta.id]))
        self.assertEqual(respuesta.status_code, 503)
        self.assertTrue(Venta.objects.filter(pk=venta.id, impreso=False).exists())

    def test_resumen_semanal_expone_ticket_y_total(self):
        resultado = procesar_venta(self.payload(), idempotency_key=uuid.uuid4(), usuario=self.usuario)
        respuesta = self.client.get(reverse('resumen_semanal'), {
            'cosechero': self.cosechero.id, 'cosecha': self.cosecha.id, 'fecha': '2026-08-04',
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()['venta_id'], resultado['venta'].id)
        self.assertEqual(respuesta.json()['total'], 37.5)

    def test_tickets_pagina_cincuenta_y_conserva_filtros(self):
        Venta.objects.bulk_create([
            Venta(
                cosechero=self.cosechero, cosecha=self.cosecha,
                fecha_venta=date(2026, 1, 1), total=Decimal(i),
            )
            for i in range(51)
        ])
        respuesta = self.client.get(reverse('tickets'), {
            'cosecha': self.cosecha.id, 'q': 'Prueba', 'desde': '2026-01-01', 'hasta': '2026-12-31',
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.context['ventas']), 50)
        self.assertContains(respuesta, 'q=Prueba')


class VentaConcurrenteTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.usuario = get_user_model().objects.create_user('concurrente', password='prueba')
        self.cosechero = Cosechero.objects.create(
            nombre='Cuenta', apellido='Concurrente', cedula='', numero_cuenta_banco=None,
            direccion='Local', telefono='', terreno_sembrado=Decimal('1.00'),
        )
        self.cosecha = Cosecha.objects.create(
            nombre='Concurrente 2026', fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31),
        )
        proveedor = Proveedor.objects.create(
            nombre='Proveedor concurrente', direccion='Local', telefono='000',
            correo_electronico='concurrente@example.com',
        )
        self.articulo = Articulo.objects.create(
            descripcion='Producto concurrente', categoria='abonos', presentacion='unidad',
            cantidad_minima_orden=1, proveedor=proveedor,
        )
        compra = Compra.objects.create(
            proveedor=proveedor, fecha_compra=date(2026, 1, 1),
            fecha_vencimiento=date(2027, 1, 1), factura='CON-1', NFC='CON-NFC',
        )
        self.lote = DetalleCompra.objects.create(
            compra=compra, articulo=self.articulo, cantidad=Decimal('10.00'),
            cantidad_restante=Decimal('10.00'), precio_compra=Decimal('50.00'),
            precio_venta_sugerido=Decimal('75.00'),
        )

    def test_dos_usuarios_comparten_una_sola_cuenta_semanal(self):
        barrera = Barrier(2)
        payload = {
            'cosechero': str(self.cosechero.id), 'cosecha': str(self.cosecha.id),
            'fecha_venta': '2026-08-04', 'detalle_articulos-TOTAL_FORMS': '1',
            'detalle_articulos-0-articulo': str(self.articulo.id),
            'detalle_articulos-0-cantidad': '0.50', 'detalle_avances-TOTAL_FORMS': '0',
        }

        def registrar():
            close_old_connections()
            usuario = get_user_model().objects.get(pk=self.usuario.pk)
            barrera.wait(timeout=5)
            resultado = procesar_venta(payload, idempotency_key=uuid.uuid4(), usuario=usuario)
            close_old_connections()
            return resultado['success']

        with ThreadPoolExecutor(max_workers=2) as executor:
            resultados = list(executor.map(lambda _: registrar(), range(2)))

        self.assertEqual(resultados, [True, True])
        self.assertEqual(Venta.objects.count(), 1)
        self.assertEqual(OperacionVenta.objects.count(), 2)
        self.lote.refresh_from_db()
        self.assertEqual(self.lote.cantidad_restante, Decimal('9.00'))
