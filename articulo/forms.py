from django import forms

from proveedor.models import Proveedor

from .models import Articulo


class ArticuloForm(forms.ModelForm):
    class Meta:
        model = Articulo
        fields = ['descripcion', 'categoria', 'presentacion', 'cantidad_minima_orden', 'proveedor']
        widgets = {'descripcion': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['proveedor'].queryset = Proveedor.objects.filter(is_active=True).order_by('nombre')
        for field in self.fields.values():
            field.widget.attrs['class'] = 'block w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-white focus:border-tobacco-500 focus:ring-tobacco-500'
