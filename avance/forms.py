# forms.py
from django import forms

class MultipleFileInput(forms.ClearableFileInput):
    # Clave: habilita selección múltiple real
    allow_multiple_selected = True


class FileUploadForm(forms.Form):
    files = forms.FileField(widget=MultipleFileInput(attrs={'multiple': True}), label='Seleccionar archivos',required=False)
