import json
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from articulo.models import Articulo
from proveedor.models import Proveedor

from .models import Compra, DetalleCompra
from .services import catalogo_articulos_por_proveedor


class CompraTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(
            username='compras-test',
            password='segura-123',
        )
        cls.proveedor = Proveedor.objects.create(
            nombre='Proveedor principal',
            direccion='Calle 1',
            telefono='8095550101',
            correo_electronico='principal@example.com',
        )
        cls.otro_proveedor = Proveedor.objects.create(
            nombre='Proveedor alterno',
            direccion='Calle 2',
            telefono='8095550102',
            correo_electronico='alterno@example.com',
        )
        cls.articulos = [
            Articulo.objects.create(
                descripcion=f'Producto {indice:02d}',
                categoria='abonos' if indice % 2 == 0 else 'fungicidas',
                presentacion=f'{indice + 1} KG',
                cantidad_minima_orden=indice + 1,
                proveedor=cls.proveedor,
            )
            for indice in range(29)
        ]
        cls.articulo_ajeno = Articulo.objects.create(
            descripcion='Producto ajeno',
            categoria='herramientas',
            presentacion='UND',
            cantidad_minima_orden=1,
            proveedor=cls.otro_proveedor,
        )
        cls.articulo_inactivo = Articulo.objects.create(
            descripcion='Producto inactivo',
            categoria='herbicidas',
            presentacion='1 LT',
            cantidad_minima_orden=1,
            proveedor=cls.proveedor,
            is_active=False,
        )
        cls.compra_historica = Compra.objects.create(
            proveedor=cls.proveedor,
            fecha_compra=date(2026, 1, 10),
            fecha_vencimiento=date(2027, 1, 10),
            factura='HIST-001',
            NFC='B0100000001',
        )
        cls.detalle_agotado = DetalleCompra.objects.create(
            compra=cls.compra_historica,
            articulo=cls.articulos[0],
            cantidad=Decimal('10.00'),
            cantidad_restante=Decimal('0.00'),
            precio_compra=Decimal('12.00'),
            precio_venta_sugerido=Decimal('18.00'),
        )
        cls.detalle_disponible = DetalleCompra.objects.create(
            compra=cls.compra_historica,
            articulo=cls.articulos[1],
            cantidad=Decimal('8.00'),
            cantidad_restante=Decimal('3.50'),
            precio_compra=Decimal('20.00'),
            precio_venta_sugerido=Decimal('28.00'),
        )

    def setUp(self):
        self.client.force_login(self.usuario)
        self.url = reverse('compras')

    def datos_compra(self, detalles=None, **cambios):
        if detalles is None:
            detalles = [{
                'articulo': self.articulos[2].id,
                'cantidad': '2.50',
                'precio_compra': '100.25',
                'precio_venta_sugerido': '140.50',
            }]
        datos = {
            'proveedor_id': str(self.proveedor.id),
            'fecha_compra': '21-08-2026',
            'fecha_vencimiento': '21-08-2027',
            'factura': 'FAC-001',
            'NFC': 'B0100000002',
            'detallesCompra': json.dumps(detalles),
        }
        datos.update(cambios)
        return datos


class CatalogoCompraTests(CompraTestBase):
    def test_catalogo_incluye_inventario_categoria_y_ultimos_precios(self):
        respuesta = self.client.get(
            reverse('obtener_articulos'),
            {'proveedor_id': self.proveedor.id},
        )

        self.assertEqual(respuesta.status_code, 200)
        articulos = {item['id']: item for item in respuesta.json()['articulos']}
        self.assertEqual(len(articulos), 29)
        self.assertEqual(articulos[self.articulos[0].id]['categoria'], 'abonos')
        self.assertEqual(articulos[self.articulos[0].id]['inventario_restante'], '0.00')
        self.assertEqual(articulos[self.articulos[0].id]['ultimo_precio_compra'], '12.00')
        self.assertEqual(articulos[self.articulos[0].id]['ultimo_precio_venta'], '18.00')
        self.assertEqual(articulos[self.articulos[1].id]['inventario_restante'], '3.50')

    def test_catalogo_se_resuelve_en_una_consulta_sin_importar_su_tamano(self):
        with CaptureQueriesContext(connection) as consultas:
            articulos = list(catalogo_articulos_por_proveedor(self.proveedor.id))

        self.assertEqual(len(articulos), 29)
        self.assertEqual(len(consultas), 1)

    def test_catalogo_excluye_articulos_inactivos_y_de_otro_proveedor(self):
        respuesta = self.client.get(
            reverse('obtener_articulos'),
            {'proveedor_id': self.proveedor.id},
        )
        ids = {item['id'] for item in respuesta.json()['articulos']}

        self.assertNotIn(self.articulo_inactivo.id, ids)
        self.assertNotIn(self.articulo_ajeno.id, ids)


class RegistroCompraTests(CompraTestBase):
    def test_registra_solo_dos_articulos_seleccionados_de_catalogo_de_29(self):
        detalles = [
            {
                'articulo': self.articulos[3].id,
                'cantidad': '2.50',
                'precio_compra': '100.25',
                'precio_venta_sugerido': '140.50',
            },
            {
                'articulo': self.articulos[20].id,
                'cantidad': '3',
                'precio_compra': '75',
                'precio_venta_sugerido': '99.99',
            },
        ]

        respuesta = self.client.post(self.url, self.datos_compra(detalles))

        self.assertEqual(respuesta.status_code, 302)
        self.assertIn('guardada=1', respuesta['Location'])
        compra = Compra.objects.get(factura='FAC-001', proveedor=self.proveedor)
        lineas = list(compra.detallecompra_set.order_by('articulo_id'))
        self.assertEqual(len(lineas), 2)
        self.assertEqual(
            {linea.articulo_id for linea in lineas},
            {self.articulos[3].id, self.articulos[20].id},
        )
        for linea in lineas:
            self.assertEqual(linea.cantidad_restante, linea.cantidad)
            self.assertTrue(linea.is_active)

    def test_acepta_cantidades_y_precios_con_dos_decimales(self):
        respuesta = self.client.post(self.url, self.datos_compra())

        self.assertEqual(respuesta.status_code, 302)
        linea = Compra.objects.get(factura='FAC-001').detallecompra_set.get()
        self.assertEqual(linea.cantidad, Decimal('2.50'))
        self.assertEqual(linea.precio_compra, Decimal('100.25'))
        self.assertEqual(linea.precio_venta_sugerido, Decimal('140.50'))

    def test_fecha_exige_formato_dia_mes_anio(self):
        respuesta = self.client.post(
            self.url,
            self.datos_compra(fecha_compra='2026-08-21'),
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertFormError(
            respuesta.context['form'],
            'fecha_compra',
            'Use una fecha válida en formato dd-mm-aaaa.',
        )
        self.assertFalse(Compra.objects.filter(factura='FAC-001').exists())

    def test_factura_repetida_del_mismo_proveedor_se_muestra_como_error(self):
        respuesta = self.client.post(
            self.url,
            self.datos_compra(factura=self.compra_historica.factura),
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertFormError(
            respuesta.context['form'],
            'factura',
            'Ya existe una compra de este proveedor con la misma factura.',
        )
        self.assertEqual(
            Compra.objects.filter(
                proveedor=self.proveedor,
                factura=self.compra_historica.factura,
            ).count(),
            1,
        )

    def test_json_malformado_y_detalle_que_no_es_lista_no_generan_error_500(self):
        casos = (
            ('{mal-json', 'El detalle de artículos no tiene un formato válido.'),
            (json.dumps({'articulo': self.articulos[2].id}), 'El detalle de artículos debe ser una lista.'),
        )
        for indice, (detalle, mensaje) in enumerate(casos):
            with self.subTest(detalle=detalle):
                respuesta = self.client.post(
                    self.url,
                    self.datos_compra(
                        factura=f'JSON-{indice}',
                        detallesCompra=detalle,
                    ),
                )
                self.assertEqual(respuesta.status_code, 400)
                self.assertContains(respuesta, mensaje, status_code=400)
                self.assertFalse(Compra.objects.filter(factura=f'JSON-{indice}').exists())

    def test_linea_invalida_conserva_valores_y_no_deja_escrituras_parciales(self):
        detalles = [
            {
                'articulo': self.articulos[4].id,
                'cantidad': '5',
                'precio_compra': '80',
                'precio_venta_sugerido': '100',
            },
            {
                'articulo': self.articulos[5].id,
                'cantidad': '2.555',
                'precio_compra': '0',
                'precio_venta_sugerido': '90',
            },
        ]

        respuesta = self.client.post(self.url, self.datos_compra(detalles))

        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(Compra.objects.filter(factura='FAC-001').exists())
        conservadas = respuesta.context['detalles_iniciales']
        self.assertEqual(len(conservadas), 2)
        self.assertEqual(conservadas[1]['cantidad'], '2.555')
        self.assertEqual(conservadas[1]['precio_compra'], '0')
        self.assertTrue(conservadas[1]['errores'])

    def test_rechazos_de_linea_son_atomicos(self):
        base = {
            'articulo': self.articulos[6].id,
            'cantidad': '2',
            'precio_compra': '10',
            'precio_venta_sugerido': '15',
        }
        casos = (
            {'articulo': self.articulo_ajeno.id},
            {'articulo': self.articulo_inactivo.id},
            {'cantidad': '0'},
            {'cantidad': '-1'},
            {'cantidad': '1.001'},
            {'precio_compra': '-1'},
            {'precio_venta_sugerido': '0'},
            {'precio_venta_sugerido': 'NaN'},
            {'precio_compra': None},
        )

        for indice, cambio in enumerate(casos):
            with self.subTest(cambio=cambio):
                detalle = {**base, **cambio}
                factura = f'INVALIDA-{indice}'
                respuesta = self.client.post(
                    self.url,
                    self.datos_compra([base, detalle], factura=factura),
                )
                self.assertEqual(respuesta.status_code, 400)
                self.assertFalse(Compra.objects.filter(factura=factura).exists())

    def test_rechaza_articulo_repetido(self):
        detalle = {
            'articulo': self.articulos[7].id,
            'cantidad': '2',
            'precio_compra': '10',
            'precio_venta_sugerido': '15',
        }
        respuesta = self.client.post(
            self.url,
            self.datos_compra([detalle, {**detalle, 'cantidad': '3'}]),
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(Compra.objects.filter(factura='FAC-001').exists())
        self.assertIn(
            'El artículo está repetido en la compra.',
            respuesta.context['detalles_iniciales'][1]['errores'],
        )

    def test_rechaza_proveedor_inactivo(self):
        self.otro_proveedor.is_active = False
        self.otro_proveedor.save(update_fields=['is_active'])
        detalle = [{
            'articulo': self.articulo_ajeno.id,
            'cantidad': '1',
            'precio_compra': '10',
            'precio_venta_sugerido': '15',
        }]

        respuesta = self.client.post(
            self.url,
            self.datos_compra(detalle, proveedor_id=str(self.otro_proveedor.id)),
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(Compra.objects.filter(factura='FAC-001').exists())


class InterfazCompraTests(CompraTestBase):
    def test_formulario_expone_fechas_textuales_busqueda_y_borrador_local(self):
        respuesta = self.client.get(self.url)

        self.assertContains(respuesta, 'placeholder="dd-mm-aaaa"', count=2)
        self.assertNotContains(respuesta, 'type="date"')
        self.assertContains(respuesta, 'localStorage.setItem(this.claveBorrador')
        self.assertContains(respuesta, 'palabras.every')
        self.assertContains(respuesta, '@keydown.enter.prevent="agregarPrimeraCoincidencia()"')
        self.assertContains(respuesta, 'Nuevo artículo')

    def test_alta_rapida_devuelve_contrato_para_agregar_articulo_a_compra(self):
        respuesta = self.client.post(reverse('articulo_alta_rapida'), {
            'descripcion': 'Producto creado en compra',
            'categoria': 'insecticidas',
            'presentacion': '500 ML',
            'cantidad_minima_orden': '2',
            'proveedor': str(self.proveedor.id),
        })

        self.assertEqual(respuesta.status_code, 201)
        objeto = respuesta.json()['object']
        self.assertEqual(objeto['proveedor_id'], self.proveedor.id)
        self.assertEqual(objeto['cantidad_minima_orden'], 2)
        self.assertEqual(objeto['inventario_restante'], 0)
        self.assertIsNone(objeto['ultimo_precio_compra'])
        self.assertIsNone(objeto['ultimo_precio_venta'])
        self.assertTrue(Articulo.objects.filter(pk=objeto['id'], is_active=True).exists())
