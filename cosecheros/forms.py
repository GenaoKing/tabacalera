# cosecheros/forms.py
from django import forms
from .models import EntregaTabaco, Cosecha


class EntregaTabacoForm(forms.ModelForm):
    class Meta:
        model = EntregaTabaco
        fields = ['cosecha','variedad', 'fecha_entrega', 'centro_largo', 'centro_corto', 'uno_medio', 'libre_pie', 'picadura', 'rezago', 'criollo']
        widgets = {
            'cosecha' : forms.Select(attrs={'class': 'form-control'}),
            'variedad': forms.Select(attrs={'class': 'form-control'}),
            'fecha_entrega': forms.DateInput(attrs={'type': 'date'}),
            'centro_largo': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'class': 'form-control'}),
            'centro_corto': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'class': 'form-control'}),
            'uno_medio': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'class': 'form-control'}),
            'libre_pie': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'class': 'form-control'}),
            'picadura': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'class': 'form-control'}),
            'rezago': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'class': 'form-control'}),
            'criollo': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'class': 'form-control'}),
        }

