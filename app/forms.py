from django.contrib.auth.forms import AuthenticationForm


class PortalAuthenticationForm(AuthenticationForm):
    """Formulario de acceso con los estilos del portal local."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        clases = (
            "block w-full rounded-lg border border-slate-700 bg-slate-900 "
            "px-3 py-2.5 text-sm text-white placeholder-slate-500 "
            "focus:border-tobacco-500 focus:ring-1 focus:ring-tobacco-500"
        )
        self.fields["username"].widget.attrs.update({
            "class": clases,
            "placeholder": "Usuario",
            "autocomplete": "username",
            "autofocus": True,
        })
        self.fields["password"].widget.attrs.update({
            "class": clases,
            "placeholder": "Contraseña",
            "autocomplete": "current-password",
        })
