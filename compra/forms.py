# forms.py

from django import forms

from .models import Compra

class CompraForm(forms.ModelForm):
    fecha_compra = forms.DateField(
        input_formats=['%d-%m-%Y'],
        error_messages={
            'required': 'La fecha de compra es obligatoria.',
            'invalid': 'Use una fecha válida en formato dd-mm-aaaa.',
        },
        widget=forms.TextInput(attrs={
            'placeholder': 'dd-mm-aaaa',
            'inputmode': 'numeric',
            'autocomplete': 'off',
            'pattern': r'\d{2}-\d{2}-\d{4}',
            'title': 'Use el formato dd-mm-aaaa',
        }),
    )
    fecha_vencimiento = forms.DateField(
        input_formats=['%d-%m-%Y'],
        error_messages={
            'required': 'La fecha de vencimiento es obligatoria.',
            'invalid': 'Use una fecha válida en formato dd-mm-aaaa.',
        },
        widget=forms.TextInput(attrs={
            'placeholder': 'dd-mm-aaaa',
            'inputmode': 'numeric',
            'autocomplete': 'off',
            'pattern': r'\d{2}-\d{2}-\d{4}',
            'title': 'Use el formato dd-mm-aaaa',
        }),
    )

    class Meta:
        model = Compra
        fields = ['fecha_compra', 'fecha_vencimiento', 'factura', 'NFC']
        widgets = {
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
        for nombre, field in self.fields.items():
            field.widget.attrs['class'] = clases
            field.widget.attrs['x-model'] = f'cabecera.{nombre}'
