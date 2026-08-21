# avance/views.py
"""
Vistas para el flujo de importación de avances.
Flujo: upload page → parse (AJAX) → preview → confirm import (AJAX)
"""
import json
import uuid
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q, Sum
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_http_methods, require_POST

from cosecheros.models import Cosecha
from ventas.models import DetalleAvance

from .forms import AvanceForm, FileUploadForm, VincularAvanceForm
from .excel import generar_plantilla_avances
from .models import Avance
from .services import (
    actualizar_avance,
    cambiar_estado_activo,
    crear_avance_individual,
    get_cosechas_list,
    import_confirmed_rows,
    parse_file_for_preview,
    vincular_avance_huerfano,
)


def _detalle_prefetch():
    return Prefetch(
        'detalleavance_set',
        queryset=DetalleAvance.objects.select_related(
            'venta__cosecha', 'venta__cosechero', 'operacion',
        ).order_by('id'),
        to_attr='vinculos',
    )


def _cosecha_actual():
    return Cosecha.objects.order_by('-fecha_inicio', '-id').first()


@login_required
def lista_avances(request):
    q = request.GET.get('q', '').strip()
    tipo = request.GET.get('tipo', '').strip()
    estado = request.GET.get('estado', '').strip()
    activo = request.GET.get('activo', 'activos').strip()
    desde = request.GET.get('desde', '').strip()
    hasta = request.GET.get('hasta', '').strip()
    sin_cosecha = request.GET.get('sin_cosecha') == '1'
    cosecha_param = request.GET.get('cosecha')
    cosecha_actual = _cosecha_actual()

    if sin_cosecha or cosecha_param == 'todas':
        cosecha_seleccionada = None
    elif cosecha_param and cosecha_param.isdigit():
        cosecha_seleccionada = Cosecha.objects.filter(pk=int(cosecha_param)).first()
    else:
        cosecha_seleccionada = cosecha_actual

    avances = Avance.objects.select_related('cosechero').prefetch_related(
        _detalle_prefetch(),
    )
    if activo == 'inactivos':
        avances = avances.filter(is_active=False)
    elif activo != 'todos':
        activo = 'activos'
        avances = avances.filter(is_active=True)

    if sin_cosecha:
        avances = avances.filter(detalleavance__isnull=True)
    elif cosecha_seleccionada:
        avances = avances.filter(
            detalleavance__venta__cosecha=cosecha_seleccionada,
            detalleavance__venta__is_active=True,
        )

    if q:
        filtro = (
            Q(cosechero__nombre__icontains=q)
            | Q(cosechero__apellido__icontains=q)
            | Q(numero__icontains=q)
            | Q(descripcion__icontains=q)
        )
        if q.isdigit():
            filtro |= Q(pk=int(q)) | Q(cosechero_id=int(q))
        avances = avances.filter(filtro)
    if tipo in dict(Avance.TIPO_AVANCE_CHOICES):
        avances = avances.filter(tipo_avance=tipo)
    else:
        tipo = ''
    if estado in dict(Avance.ESTADOS_CHOICES):
        avances = avances.filter(estado=estado)
    else:
        estado = ''
    fecha_desde = parse_date(desde)
    fecha_hasta = parse_date(hasta)
    if fecha_desde:
        avances = avances.filter(fecha__gte=fecha_desde)
    if fecha_hasta:
        avances = avances.filter(fecha__lte=fecha_hasta)

    avances = avances.distinct()
    resumen = avances.aggregate(total=Sum('monto_pagado'))
    resumen['cantidad'] = avances.count()
    paginator = Paginator(avances.order_by('-fecha', '-id'), 50)
    page_obj = paginator.get_page(request.GET.get('page'))

    filtros = request.GET.copy()
    filtros.pop('page', None)
    return render(request, 'avances/lista.html', {
        'avances': page_obj.object_list,
        'page_obj': page_obj,
        'filtros_query': filtros.urlencode(),
        'cosechas': Cosecha.objects.all().order_by('-fecha_inicio', '-id'),
        'cosecha_seleccionada': cosecha_seleccionada,
        'q': q,
        'tipo': tipo,
        'estado': estado,
        'activo': activo,
        'desde': desde if fecha_desde else '',
        'hasta': hasta if fecha_hasta else '',
        'sin_cosecha': sin_cosecha,
        'resumen': resumen,
        'tipos': Avance.TIPO_AVANCE_CHOICES,
        'estados': Avance.ESTADOS_CHOICES,
    })


@login_required
def detalle_avance(request, avance_id):
    avance = get_object_or_404(
        Avance.objects.select_related('cosechero').prefetch_related(_detalle_prefetch()),
        pk=avance_id,
    )
    return render(request, 'avances/detalle.html', {'avance': avance})


@login_required
def nuevo_avance(request):
    cosecha = _cosecha_actual()
    initial = {
        'cosecha': cosecha,
        'fecha': date.today(),
        'estado': 'realizado',
        'idempotency_key': uuid.uuid4(),
    }
    form = AvanceForm(
        request.POST or None,
        initial=initial,
        cosecha_inicial=cosecha,
        require_cosecha=True,
    )
    if request.method == 'POST' and form.is_valid():
        resultado = crear_avance_individual(
            form.cleaned_data,
            idempotency_key=form.cleaned_data.get('idempotency_key'),
            usuario=request.user,
        )
        if resultado.get('success'):
            avance = resultado['avance']
            messages.success(request, f'Avance #{avance.id} registrado correctamente.')
            return redirect('avance_detalle', avance_id=avance.id)
        for error in resultado.get('errors', ['No fue posible registrar el avance.']):
            form.add_error(None, error)
    return render(request, 'avances/form.html', {
        'form': form,
        'titulo': 'Nuevo avance',
        'es_edicion': False,
        'volver_url': reverse('avances'),
    }, status=400 if request.method == 'POST' else 200)


@login_required
def editar_avance(request, avance_id):
    avance = get_object_or_404(
        Avance.objects.select_related('cosechero').prefetch_related(_detalle_prefetch()),
        pk=avance_id,
    )
    if not avance.is_active:
        messages.error(request, 'Restaure el avance antes de editarlo.')
        return redirect('avance_detalle', avance_id=avance.id)
    vinculo = avance.vinculos[0] if len(avance.vinculos) == 1 else None
    cosecha = vinculo.venta.cosecha if vinculo else None
    form = AvanceForm(
        request.POST or None,
        instance=avance,
        cosecha_inicial=cosecha,
        require_cosecha=bool(vinculo),
    )
    if request.method == 'POST' and form.is_valid():
        try:
            actualizar_avance(avance.id, form.cleaned_data)
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, f'Avance #{avance.id} actualizado correctamente.')
            return redirect('avance_detalle', avance_id=avance.id)
    return render(request, 'avances/form.html', {
        'form': form,
        'titulo': f'Editar avance #{avance.id}',
        'es_edicion': True,
        'avance': avance,
        'vinculo': vinculo,
        'volver_url': reverse('avance_detalle', args=[avance.id]),
    }, status=400 if request.method == 'POST' else 200)


@login_required
@require_POST
def desactivar_avance(request, avance_id):
    avance = get_object_or_404(Avance, pk=avance_id, is_active=True)
    cambiar_estado_activo(avance.id, activo=False)
    messages.success(request, f'Avance #{avance.id} desactivado y excluido de las cuentas.')
    return redirect('avance_detalle', avance_id=avance.id)


@login_required
@require_POST
def restaurar_avance(request, avance_id):
    avance = get_object_or_404(Avance, pk=avance_id, is_active=False)
    cambiar_estado_activo(avance.id, activo=True)
    messages.success(request, f'Avance #{avance.id} restaurado y reincorporado a las cuentas.')
    return redirect('avance_detalle', avance_id=avance.id)


@login_required
def vincular_avance(request, avance_id):
    avance = get_object_or_404(
        Avance.objects.select_related('cosechero').prefetch_related(_detalle_prefetch()),
        pk=avance_id,
    )
    if avance.vinculos:
        messages.error(request, 'Este avance ya está vinculado a una cuenta semanal.')
        return redirect('avance_detalle', avance_id=avance.id)
    if not avance.is_active:
        messages.error(request, 'Restaure el avance antes de vincularlo.')
        return redirect('avance_detalle', avance_id=avance.id)
    form = VincularAvanceForm(request.POST or None, initial={
        'cosecha': _cosecha_actual(),
        'cosechero': avance.cosechero,
        'fecha': avance.fecha,
    })
    if request.method == 'POST' and form.is_valid():
        try:
            vincular_avance_huerfano(avance.id, **form.cleaned_data)
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, f'Avance #{avance.id} vinculado correctamente.')
            return redirect('avance_detalle', avance_id=avance.id)
    return render(request, 'avances/vincular.html', {
        'avance': avance,
        'form': form,
    }, status=400 if request.method == 'POST' else 200)


@login_required
def upload_redirect(request):
    return redirect('avances_importar')


@login_required
def upload_view(request):
    """Renderiza la página de importación de avances."""
    cosechas = get_cosechas_list()
    return render(request, 'upload.html', {
        'form': FileUploadForm(),
        'cosechas_json': json.dumps(cosechas),
    })


@login_required
@require_http_methods(["GET"])
def descargar_plantilla(request):
    """Descarga la plantilla XLSX con el catálogo vigente de cosecheros."""
    filename = f'plantilla_avances_{date.today():%d-%m-%Y}.xlsx'
    return FileResponse(
        generar_plantilla_avances(),
        as_attachment=True,
        filename=filename,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


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
