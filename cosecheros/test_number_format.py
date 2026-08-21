from decimal import Decimal

from django.template import Context, Template
from django.test import SimpleTestCase

from app.number_format import format_money, format_number


class NumberFormatTests(SimpleTestCase):
    def test_formato_compartido_usa_miles_y_dos_decimales(self):
        self.assertEqual(format_number(Decimal('10000')), '10,000.00')
        self.assertEqual(format_number(Decimal('1234.567')), '1,234.57')
        self.assertEqual(format_number(Decimal('-2500.5')), '-2,500.50')
        self.assertEqual(format_money(Decimal('10000'), 'RD$ '), 'RD$ 10,000.00')

    def test_filtro_de_plantilla_aplica_la_misma_convencion(self):
        template = Template('{% load number_format %}{{ value|number_2 }}')

        rendered = template.render(Context({'value': Decimal('10000')}))

        self.assertEqual(rendered, '10,000.00')
