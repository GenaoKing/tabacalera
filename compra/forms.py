# forms.py

from django import forms
from django.forms import inlineformset_factory
from .models import Compra, DetalleCompra, Proveedor, Articulo

class CompraForm(forms.ModelForm):
    class Meta:
        model = Compra
        fields = ['fecha_compra', 'fecha_vencimiento','factura','NFC']
        widgets = {
            'fecha_compra': forms.DateInput(attrs={'type': 'date'}),
            'fecha_vencimiento': forms.DateInput(attrs={'type': 'date'}),
            'factura': forms.TextInput(),
            'NFC': forms.TextInput(),
        }
   


DetalleCompraFormset = inlineformset_factory(
    Compra, DetalleCompra, 
    fields=('articulo', 'cantidad', 'precio_compra', 'precio_venta_sugerido','cantidad_restante')
)
