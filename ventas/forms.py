from django import forms
from .models import Venta, DetalleArticulo, DetalleAvance
from articulo.models import Articulo
from avance.models import Avance

class VentaForm(forms.ModelForm):
    class Meta:
        model = Venta
        fields = ['cosechero','fecha_venta','cosecha']
        widgets = {
            'cosecha' : forms.Select(attrs={'class': 'form-control'}),
            'cosechero': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Buscar cosechero...'}),
            'fecha_venta': forms.DateInput(attrs={'type': 'date'}),
        }

class DetalleArticuloForm(forms.ModelForm):
    class Meta:
        model = DetalleArticulo
        fields = ['articulo', 'cantidad', 'precio_venta_final']
        widgets = {
            'articulo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Buscar artículo...'}),
            'cantidad': forms.NumberInput(attrs={'class': 'form-control'}),
            'precio_venta_final': forms.NumberInput(attrs={'class': 'form-control'}),
        }

class DetalleAvanceForm(forms.ModelForm):
    class Meta:
        model = DetalleAvance
        fields = ['avance', 'monto']
        widgets = {
            'avance': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Buscar avance...'}),
            'monto': forms.NumberInput(attrs={'class': 'form-control'}),
        }
