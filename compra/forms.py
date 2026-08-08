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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        clases = (
            'block w-full rounded-lg border border-slate-700 bg-slate-950 '
            'px-3 py-2.5 text-sm text-white placeholder-slate-500 '
            'focus:border-tobacco-500 focus:ring-1 focus:ring-tobacco-500'
        )
        for field in self.fields.values():
            field.widget.attrs['class'] = clases
   


DetalleCompraFormset = inlineformset_factory(
    Compra, DetalleCompra, 
    fields=('articulo', 'cantidad', 'precio_compra', 'precio_venta_sugerido','cantidad_restante')
)
