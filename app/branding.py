"""Recursos de identidad visual compartidos por web, PDF e impresión."""
from pathlib import Path

from django.contrib.staticfiles import finders


BRAND_NAME = 'Tabacalera Genao S.R.L.'
BRAND_LOGO_STATIC = 'img/tabacalera-genao-logo.png'


def get_brand_logo_path() -> Path:
    """Resuelve el logo mediante los buscadores de estáticos de Django."""
    path = finders.find(BRAND_LOGO_STATIC)
    if not path:
        raise FileNotFoundError(
            f'No se encontró el logo corporativo estático: {BRAND_LOGO_STATIC}'
        )
    return Path(path)
