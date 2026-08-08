from django import forms
from .models import Cosechero, EntregaTabaco, Cosecha


class CosecheroForm(forms.ModelForm):
    class Meta:
        model = Cosechero
        fields = [
            'nombre', 'apellido', 'cedula', 'numero_cuenta_banco',
            'direccion', 'telefono', 'terreno_sembrado',
        ]
        widgets = {
            'direccion': forms.Textarea(attrs={'rows': 3}),
            'terreno_sembrado': forms.NumberInput(attrs={'min': '0', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        clases = (
            'block w-full rounded-lg border border-slate-700 bg-slate-900 '
            'px-3 py-2.5 text-sm text-white focus:border-tobacco-500 focus:ring-tobacco-500'
        )
        for field in self.fields.values():
            field.widget.attrs['class'] = clases

    def clean_numero_cuenta_banco(self):
        return self.cleaned_data.get('numero_cuenta_banco') or None


class EntregaTabacoForm(forms.ModelForm):
    class Meta:
        model = EntregaTabaco
        fields = ['cosecha','variedad', 'fecha_entrega', 'centro_largo', 'centro_corto', 'uno_medio', 'libre_pie', 'picadura', 'rezago', 'criollo']
        widgets = {
            'cosecha': forms.Select(),
            'variedad': forms.Select(),
            'fecha_entrega': forms.DateInput(attrs={'type': 'date'}),
            'centro_largo': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'centro_corto': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'uno_medio': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'libre_pie': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'picadura': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'rezago': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'criollo': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        clases = (
            'block w-full rounded-lg border border-slate-700 bg-slate-900 '
            'px-3 py-2 text-sm text-white focus:border-tobacco-500 '
            'focus:ring-1 focus:ring-tobacco-500'
        )
        for field in self.fields.values():
            field.widget.attrs['class'] = clases

