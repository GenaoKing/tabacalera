# avance/forms.py
from django import forms


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