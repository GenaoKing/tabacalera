# avance/forms.py
from decimal import Decimal

from django import forms
from django.core.validators import MinValueValidator
from django.db.models import Q

from cosecheros.models import Cosecha, Cosechero

from .models import Avance


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class FileUploadForm(forms.Form):
    files = forms.FileField(
        widget=MultipleFileInput(attrs={
            'multiple': False,  # Ahora procesamos uno a la vez con preview
            'accept': '.csv,.xlsx,.xls',
        }),
        label='Seleccionar archivo',
        required=False,
    )


INPUT_CLASS = (
    'block w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2.5 '
    'text-sm text-white focus:border-tobacco-500 focus:ring-tobacco-500'
)


class AvanceForm(forms.ModelForm):
    """Formulario operativo; la cosecha se materializa mediante DetalleAvance."""

    cosecha = forms.ModelChoiceField(queryset=Cosecha.objects.none(), label='Cosecha')
    idempotency_key = forms.UUIDField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = Avance
        fields = [
            'cosecha', 'cosechero', 'fecha', 'tipo_avance', 'numero',
            'monto_pagado', 'descripcion', 'estado',
        ]
        labels = {
            'monto_pagado': 'Monto',
            'tipo_avance': 'Tipo de avance',
            'numero': 'Número o referencia',
            'estado': 'Estado documental',
        }
        widgets = {
            'fecha': forms.DateInput(attrs={'type': 'date'}),
            'monto_pagado': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'descripcion': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, cosecha_inicial=None, require_cosecha=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cosecha'].required = require_cosecha
        self.fields['cosecha'].queryset = Cosecha.objects.all().order_by('-fecha_inicio', '-id')

        filtro_cosecheros = Q(is_active=True)
        if self.instance and self.instance.pk:
            filtro_cosecheros |= Q(pk=self.instance.cosechero_id)
        self.fields['cosechero'].queryset = Cosechero.objects.filter(
            filtro_cosecheros,
        ).order_by('nombre', 'apellido')

        if cosecha_inicial is not None and not self.is_bound:
            self.fields['cosecha'].initial = cosecha_inicial

        self.fields['estado'].help_text = (
            'Este estado es informativo. Para excluir el monto de las cuentas, '
            'use la acción Desactivar.'
        )
        self.fields['numero'].required = False
        self.fields['descripcion'].required = False
        self.fields['monto_pagado'].validators.append(MinValueValidator(Decimal('0.01')))
        for name, field in self.fields.items():
            if name != 'idempotency_key':
                field.widget.attrs['class'] = INPUT_CLASS

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('tipo_avance') in {'deposito', 'efectivo'}:
            cleaned['estado'] = 'realizado'
        return cleaned


class VincularAvanceForm(forms.Form):
    cosecha = forms.ModelChoiceField(
        queryset=Cosecha.objects.none(), label='Cosecha confirmada',
    )
    cosechero = forms.ModelChoiceField(
        queryset=Cosechero.objects.none(), label='Cosechero confirmado',
    )
    fecha = forms.DateField(
        label='Fecha real del avance',
        widget=forms.DateInput(attrs={'type': 'date'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cosecha'].queryset = Cosecha.objects.all().order_by('-fecha_inicio', '-id')
        self.fields['cosechero'].queryset = Cosechero.objects.filter(
            is_active=True,
        ).order_by('nombre', 'apellido')
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CLASS
