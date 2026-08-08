# avance/views.py
"""
Vistas para el flujo de importación de avances.
Flujo: upload page → parse (AJAX) → preview → confirm import (AJAX)
"""
import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required

from .forms import FileUploadForm
from .services import parse_file_for_preview, import_confirmed_rows, get_cosechas_list


@login_required
def upload_view(request):
    """Renderiza la página de importación de avances."""
    cosechas = get_cosechas_list()
    return render(request, 'upload.html', {
        'form': FileUploadForm(),
        'cosechas_json': json.dumps(cosechas),
    })


@login_required
@require_http_methods(["POST"])
def parse_file_view(request):
    """
    AJAX: Recibe el archivo, lo parsea y retorna el preview JSON.
    No importa nada todavía — solo parsea y valida.
    """
    files = request.FILES.getlist('files')

    if not files:
        return JsonResponse({
            'success': False,
            'error': 'Seleccione al menos un archivo.'
        }, status=400)

    f = files[0]

    try:
        preview_data = parse_file_for_preview(f)
        return JsonResponse({
            'success': True,
            'data': preview_data,
        })
    except ValueError as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error inesperado al procesar el archivo: {str(e)}',
        }, status=500)


@login_required
@require_http_methods(["POST"])
def import_rows_view(request):
    """
    AJAX: Recibe las filas confirmadas por el usuario y las importa.
    Espera JSON con { rows: [...], cosecha_id: int, descripcion_default: str }
    """
    try:
        body = json.loads(request.body)
        rows = body.get('rows', [])
        cosecha_id = body.get('cosecha_id')
        descripcion_default = body.get('descripcion_default', 'Avance a cosecha')

        if not rows:
            return JsonResponse({
                'success': False,
                'error': 'No se recibieron filas para importar.',
            }, status=400)

        if not cosecha_id:
            return JsonResponse({
                'success': False,
                'error': 'Debe seleccionar una cosecha.',
            }, status=400)

        # Validar que todas las filas tengan datos mínimos
        for i, row in enumerate(rows):
            if not row.get('cosechero_id'):
                return JsonResponse({
                    'success': False,
                    'error': f'Fila {row.get("index", i)}: falta cosechero.',
                }, status=400)
            if not row.get('fecha'):
                return JsonResponse({
                    'success': False,
                    'error': f'Fila {row.get("index", i)}: falta fecha.',
                }, status=400)
            if not row.get('monto'):
                return JsonResponse({
                    'success': False,
                    'error': f'Fila {row.get("index", i)}: falta monto.',
                }, status=400)

        stats = import_confirmed_rows(
            rows=rows,
            cosecha_id=int(cosecha_id),
            descripcion_default=descripcion_default,
        )

        return JsonResponse({
            'success': True,
            'stats': stats,
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'JSON inválido.',
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error al importar: {str(e)}',
        }, status=500)