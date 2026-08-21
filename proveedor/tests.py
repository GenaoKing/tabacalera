from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from articulo.models import Articulo
from .models import Proveedor


class ListadoProveedorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user('proveedores', password='prueba')
        cls.proveedor = Proveedor.objects.create(
            nombre='Casa Agrícola', direccion='Local', telefono='809-555-1000',
            correo_electronico='casa@example.com',
        )
        cls.articulo = Articulo.objects.create(
            descripcion='Abono especial', categoria='abonos', presentacion='Saco',
            cantidad_minima_orden=1, proveedor=cls.proveedor,
        )
        cls.inactivo = Articulo.objects.create(
            descripcion='Producto retirado', categoria='abonos', presentacion='Saco',
            cantidad_minima_orden=1, proveedor=cls.proveedor, is_active=False,
        )

    def setUp(self):
        self.client.force_login(self.usuario)

    def test_lista_muestra_articulos_activos_del_proveedor(self):
        response = self.client.get(reverse('proveedores'))

        self.assertEqual(response.status_code, 200)
        proveedor = response.context['objetos'].get(pk=self.proveedor.pk)
        self.assertEqual(proveedor.articulos_activos, [self.articulo])
        self.assertContains(response, 'Abono especial')
        self.assertContains(response, reverse('articulo_editar', args=[self.articulo.id]))
        self.assertNotContains(response, 'Producto retirado')

# Create your tests here.
