import csv
import io
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from articulo.models import Articulo
from avance.models import Avance
from proveedor.models import Proveedor
from ventas.models import DetalleArticulo, DetalleAvance, OperacionVenta, Venta

from .models import Cosecha, Cosechero, EntregaTabaco, PrecioVariedadCosecha
from .services import calcular_resumenes_cosecha
from app.branding import BRAND_LOGO_STATIC, get_brand_logo_path


class UniversoFinancieroTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user('finanzas', password='prueba')
        cls.cosecha = Cosecha.objects.create(
            nombre='Universo 2026', fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31),
        )
        cls.proveedor = Proveedor.objects.create(
            nombre='Proveedor financiero', direccion='Local', telefono='000',
            correo_electronico='finanzas@example.com',
        )
        cls.articulo = Articulo.objects.create(
            descripcion='Insumo financiero', categoria='abonos', presentacion='unidad',
            cantidad_minima_orden=1, proveedor=cls.proveedor,
        )
        PrecioVariedadCosecha.objects.create(
            cosecha=cls.cosecha, variedad='Corojo Original',
            precio_centro_largo=Decimal('10.00'),
        )

        def cosechero(nombre):
            return Cosechero.objects.create(
                nombre=nombre, apellido='Prueba', cedula='', numero_cuenta_banco=None,
                direccion='Local', telefono='', terreno_sembrado=Decimal('1.00'),
            )

        cls.solo_articulo = cosechero('Artículo')
        cls.solo_entrega = cosechero('Entrega')
        cls.solo_avance = cosechero('Avance')
        cls.combinado = cosechero('Combinado')
        cls.sin_precio = cosechero('Sin precio')
        cls.venta_vacia = cosechero('Venta vacía')

        venta_articulo = Venta.objects.create(
            cosechero=cls.solo_articulo, cosecha=cls.cosecha,
            fecha_venta=date(2026, 1, 10), total=Decimal('25.00'),
        )
        DetalleArticulo.objects.create(
            venta=venta_articulo, articulo=cls.articulo,
            cantidad=Decimal('2.00'), precio_venta_final=Decimal('12.50'),
        )

        EntregaTabaco.objects.create(
            cosechero=cls.solo_entrega, cosecha=cls.cosecha,
            variedad='Corojo Original', fecha_entrega=date(2026, 2, 1),
            centro_largo=Decimal('10.00'),
        )

        venta_avance = Venta.objects.create(
            cosechero=cls.solo_avance, cosecha=cls.cosecha,
            fecha_venta=date(2026, 3, 7), total=Decimal('30.00'),
        )
        avance = Avance.objects.create(
            cosechero=cls.solo_avance, monto_pagado=Decimal('99.99'),
            fecha=date(2026, 3, 2), descripcion='Avance vinculado',
            tipo_avance='efectivo', numero='A-1',
        )
        DetalleAvance.objects.create(
            venta=venta_avance, avance=avance, monto=Decimal('30.00'),
        )

        venta_combinada = Venta.objects.create(
            cosechero=cls.combinado, cosecha=cls.cosecha,
            fecha_venta=date(2026, 4, 4), total=Decimal('15.00'),
        )
        operacion = OperacionVenta.objects.create(
            venta=venta_combinada, fecha_movimiento=date(2026, 4, 1),
            huella_payload='a' * 64, total_movimiento=Decimal('10.00'),
        )
        DetalleArticulo.objects.create(
            venta=venta_combinada, operacion=operacion, articulo=cls.articulo,
            cantidad=Decimal('1.00'), precio_venta_final=Decimal('10.00'),
        )
        avance_combinado = Avance.objects.create(
            cosechero=cls.combinado, monto_pagado=Decimal('5.00'),
            fecha=date(2026, 4, 1), descripcion='Avance combinado',
            tipo_avance='cheque', numero='A-2',
        )
        DetalleAvance.objects.create(
            venta=venta_combinada, avance=avance_combinado, monto=Decimal('5.00'),
        )
        EntregaTabaco.objects.create(
            cosechero=cls.combinado, cosecha=cls.cosecha,
            variedad='Corojo Original', fecha_entrega=date(2026, 4, 1),
            centro_largo=Decimal('10.00'),
        )

        EntregaTabaco.objects.create(
            cosechero=cls.sin_precio, cosecha=cls.cosecha,
            variedad='HVA', fecha_entrega=date(2026, 5, 1),
            centro_largo=Decimal('2.00'),
        )
        Venta.objects.create(
            cosechero=cls.venta_vacia, cosecha=cls.cosecha,
            fecha_venta=date(2026, 6, 6), total=Decimal('0.00'),
        )

        # No pertenece a ninguna cosecha mientras no exista DetalleAvance.
        Avance.objects.create(
            cosechero=cls.solo_articulo, monto_pagado=Decimal('500.00'),
            fecha=date(2026, 7, 1), descripcion='Huérfano',
            tipo_avance='efectivo', numero='H-1',
        )

    def setUp(self):
        self.client.force_login(self.usuario)

    def filas(self):
        return {
            fila['cosechero'].id: fila
            for fila in calcular_resumenes_cosecha(self.cosecha.id)
        }

    def test_union_incluye_cada_fuente_sin_duplicar(self):
        filas = self.filas()
        self.assertEqual(len(filas), 6)
        self.assertEqual(filas[self.solo_articulo.id]['gastos'], Decimal('25.0000'))
        self.assertEqual(filas[self.solo_entrega.id]['produccion'], Decimal('100.000000'))
        self.assertEqual(filas[self.solo_avance.id]['gastos_avances'], Decimal('30.00'))
        self.assertEqual(filas[self.combinado.id]['gastos'], Decimal('15.0000'))
        self.assertEqual(filas[self.combinado.id]['produccion'], Decimal('100.000000'))
        self.assertEqual(filas[self.solo_articulo.id]['gasto_promedio_tarea'], Decimal('25.0000'))
        self.assertEqual(filas[self.solo_entrega.id]['produccion_promedio_tarea'], Decimal('100.000000'))
        self.assertEqual(filas[self.solo_entrega.id]['quintales_producidos'], Decimal('10.00'))
        self.assertEqual(filas[self.solo_entrega.id]['quintales_promedio_tarea'], Decimal('10.00'))

    def test_importes_son_decimal_y_huerfano_no_se_contabiliza(self):
        fila = self.filas()[self.solo_articulo.id]
        for campo in (
            'gastos_articulos', 'gastos_avances', 'gastos', 'produccion', 'saldo',
            'tareas_sembradas', 'gasto_promedio_tarea', 'produccion_promedio_tarea',
            'quintales_producidos', 'quintales_promedio_tarea',
        ):
            self.assertIsInstance(fila[campo], Decimal)
        self.assertEqual(fila['gastos_avances'], Decimal('0'))
        self.assertEqual(Decimal('0.1') + Decimal('0.2'), Decimal('0.3'))

    def test_sin_produccion_requiere_gastos_y_cero_entregas(self):
        filas = self.filas()
        self.assertTrue(filas[self.solo_articulo.id]['sin_produccion_entregada'])
        self.assertTrue(filas[self.solo_avance.id]['sin_produccion_entregada'])
        self.assertFalse(filas[self.sin_precio.id]['sin_produccion_entregada'])
        self.assertFalse(filas[self.venta_vacia.id]['sin_produccion_entregada'])
        self.assertEqual(filas[self.sin_precio.id]['entregas_sin_precio'], 1)

    def test_ultima_actividad_exacta_semanal_y_empate(self):
        filas = self.filas()
        historica = filas[self.solo_articulo.id]
        self.assertEqual(historica['ultima_actividad_fecha'], date(2026, 1, 10))
        self.assertEqual(historica['ultima_actividad_tipos'], ('articulo',))
        self.assertEqual(historica['ultima_actividad_precision'], 'cierre_semanal')

        combinada = filas[self.combinado.id]
        self.assertEqual(combinada['ultima_actividad_fecha'], date(2026, 4, 1))
        self.assertEqual(combinada['ultima_actividad_tipos'], ('entrega', 'avance', 'articulo'))
        self.assertEqual(combinada['ultima_actividad_precision'], 'exacta')

        vacia = filas[self.venta_vacia.id]
        self.assertEqual(vacia['ultima_actividad_tipos'], ('venta',))
        self.assertEqual(vacia['ultima_actividad_precision'], 'cierre_semanal')

    def test_precision_mixta_si_coinciden_fecha_exacta_y_semanal(self):
        venta = Venta.objects.create(
            cosechero=self.combinado, cosecha=self.cosecha,
            fecha_venta=date(2026, 4, 1), total=Decimal('1.00'),
        )
        DetalleArticulo.objects.create(
            venta=venta, articulo=self.articulo,
            cantidad=Decimal('1.00'), precio_venta_final=Decimal('1.00'),
        )
        fila = self.filas()[self.combinado.id]
        self.assertEqual(fila['ultima_actividad_precision'], 'mixta')

    def test_consultas_no_crecen_con_cosecheros(self):
        with self.assertNumQueries(6):
            list(calcular_resumenes_cosecha(self.cosecha.id))

    def test_quintales_usan_la_misma_tara_que_la_valorizacion(self):
        entrega = EntregaTabaco.objects.get(cosechero=self.solo_entrega)
        entrega.centro_largo = Decimal('10.50')
        entrega.save(update_fields=['centro_largo'])

        fila = self.filas()[self.solo_entrega.id]

        self.assertEqual(fila['quintales_producidos'], Decimal('10.900'))
        self.assertEqual(fila['produccion'], Decimal('109.0000'))

    def test_dashboard_alerta_filtro_y_csv_coinciden(self):
        respuesta = self.client.get(reverse('dashboard'), {'cosecha': self.cosecha.id})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.context['sin_produccion']), 2)
        self.assertEqual(respuesta.context['total_sin_produccion'], Decimal('55.0000'))
        self.assertEqual(respuesta.context['total_nos_deben'], Decimal('55.0000'))
        self.assertContains(respuesta, 'Sin producción entregada')
        self.assertContains(respuesta, 'Indicadores por tarea', count=2)
        self.assertContains(respuesta, 'Gasto/tarea')
        self.assertContains(respuesta, 'Producción/tarea')
        self.assertContains(respuesta, 'Quintales/tarea')

        filtrada = self.client.get(reverse('dashboard'), {
            'cosecha': self.cosecha.id, 'sin_produccion': '1',
        })
        self.assertEqual(len(filtrada.context['nos_deben']), 2)
        self.assertEqual(filtrada.context['les_debemos'], [])

        csv_response = self.client.get(reverse('dashboard_csv'), {'cosecha': self.cosecha.id})
        filas_csv = list(csv.DictReader(io.StringIO(csv_response.content.decode('utf-8-sig'))))
        self.assertEqual(len(filas_csv), 6)
        articulo_csv = next(f for f in filas_csv if int(f['Cosechero ID']) == self.solo_articulo.id)
        self.assertEqual(articulo_csv['Artículos'], '25.00')
        self.assertEqual(articulo_csv['Avances'], '0.00')
        self.assertEqual(articulo_csv['Sin producción entregada'], 'Sí')
        self.assertEqual(articulo_csv['Tareas'], '1.00')
        self.assertEqual(articulo_csv['Gasto por tarea'], '25.00')
        self.assertEqual(articulo_csv['Producción por tarea'], '0.00')
        self.assertEqual(articulo_csv['Quintales por tarea'], '0.00')

    def test_dashboard_no_divide_entre_cero_si_no_hay_tareas(self):
        Cosechero.objects.filter(pk=self.solo_articulo.id).update(terreno_sembrado=Decimal('0'))

        respuesta = self.client.get(reverse('dashboard'), {'cosecha': self.cosecha.id})

        self.assertEqual(respuesta.status_code, 200)
        fila = next(
            item for item in respuesta.context['nos_deben']
            if item['cosechero'].id == self.solo_articulo.id
        )
        self.assertIsNone(fila['gasto_promedio_tarea'])
        self.assertIsNone(fila['produccion_promedio_tarea'])
        self.assertIsNone(fila['quintales_promedio_tarea'])
        self.assertContains(respuesta, 'Sin tareas registradas', count=1)

    def test_pdf_individual_se_genera_desde_el_resumen_comun(self):
        respuesta = self.client.get(reverse(
            'reporte_cosechero', args=[self.combinado.id, self.cosecha.id],
        ))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'application/pdf')


class IdentidadVisualTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user('marca', password='prueba')

    def test_logo_corporativo_esta_disponible_en_portal_login_y_admin(self):
        logo_path = get_brand_logo_path()
        self.assertTrue(logo_path.exists())
        self.assertEqual(finders.find(BRAND_LOGO_STATIC), str(logo_path))

        login = self.client.get(reverse('login'))
        self.assertContains(login, '/static/img/tabacalera-genao-logo.png', count=2)

        self.client.force_login(self.usuario)
        portal = self.client.get(reverse('dashboard'))
        self.assertContains(portal, '/static/img/tabacalera-genao-logo.png', count=2)

        admin_login = self.client.get('/admin/login/')
        self.assertContains(admin_login, '/static/img/tabacalera-genao-logo.png')
