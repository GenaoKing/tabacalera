import csv
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

from app.number_format import format_number
from cosecheros.models import Cosecha
from cosecheros.services import calcular_saldos_cosecha

@login_required
def dashboard(request):
    cosechas = Cosecha.objects.all().order_by('-fecha_inicio')
    cosecha_id = request.GET.get('cosecha')
    cosecha = get_object_or_404(Cosecha, pk=cosecha_id) if cosecha_id else cosechas.first()
    saldos_completos = calcular_saldos_cosecha(cosecha.id) if cosecha else []
    sin_produccion = [fila for fila in saldos_completos if fila['sin_produccion_entregada']]
    total_sin_produccion = sum((fila['gastos'] for fila in sin_produccion), Decimal('0'))
    cuentas_sin_precio = [fila for fila in saldos_completos if fila['entregas_sin_precio'] > 0]

    saldos = saldos_completos
    q = request.GET.get('q', '').strip().lower()
    if q:
        saldos = [fila for fila in saldos if q in str(fila['cosechero']).lower()]
    solo_sin_produccion = request.GET.get('sin_produccion') == '1'
    if solo_sin_produccion:
        saldos = [fila for fila in saldos if fila['sin_produccion_entregada']]

    nos_deben = [fila for fila in saldos if fila['saldo'] > 0]
    les_debemos = [fila for fila in saldos if fila['saldo'] < 0]
    for fila in nos_deben:
        fila['saldo_mostrar'] = fila['saldo']
    for fila in les_debemos:
        fila['saldo_mostrar'] = -fila['saldo']
    nos_deben.sort(key=lambda fila: fila['saldo'], reverse=True)
    les_debemos.sort(key=lambda fila: fila['saldo'])
    total_nos_deben = sum((fila['saldo'] for fila in nos_deben), Decimal('0'))
    total_les_debemos = sum((-fila['saldo'] for fila in les_debemos), Decimal('0'))
    context = {
        'cosechas': cosechas,
        'cosecha': cosecha,
        'q': request.GET.get('q', '').strip(),
        'solo_sin_produccion': solo_sin_produccion,
        'nos_deben': nos_deben,
        'les_debemos': les_debemos,
        'total_nos_deben': total_nos_deben,
        'total_les_debemos': total_les_debemos,
        'balance_neto': total_nos_deben - total_les_debemos,
        'sin_produccion': sin_produccion,
        'total_sin_produccion': total_sin_produccion,
        'cuentas_sin_precio': cuentas_sin_precio,
    }
    return render(request, 'dashboard/dashboard.html', context)


@login_required
def exportar_csv(request):
    cosecha = get_object_or_404(Cosecha, pk=request.GET.get('cosecha'))
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="saldos_{cosecha.id}.csv"'
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow([
        'Cosechero ID', 'Cosechero', 'Artículos', 'Avances', 'Gastos',
        'Producción', 'Saldo', 'Estado', 'Cantidad entregas',
        'Sin producción entregada', 'Entregas sin precio',
        'Tareas', 'Gasto por tarea', 'Producción por tarea',
        'Quintales producidos', 'Quintales por tarea',
        'Última actividad', 'Tipos de última actividad', 'Precisión de fecha',
    ])
    for fila in calcular_saldos_cosecha(cosecha.id):
        estado = (
            'Nos debe' if fila['saldo'] > 0
            else 'Le debemos' if fila['saldo'] < 0
            else 'Saldado'
        )
        writer.writerow([
            fila['cosechero'].id,
            str(fila['cosechero']),
            format_number(fila['gastos_articulos']),
            format_number(fila['gastos_avances']),
            format_number(fila['gastos']),
            format_number(fila['produccion']),
            format_number(fila['saldo']),
            estado,
            fila['cantidad_entregas'],
            'Sí' if fila['sin_produccion_entregada'] else 'No',
            fila['entregas_sin_precio'],
            format_number(fila['tareas_sembradas']),
            format_number(fila['gasto_promedio_tarea']) if fila['gasto_promedio_tarea'] is not None else '',
            format_number(fila['produccion_promedio_tarea']) if fila['produccion_promedio_tarea'] is not None else '',
            format_number(fila['quintales_producidos']),
            format_number(fila['quintales_promedio_tarea']) if fila['quintales_promedio_tarea'] is not None else '',
            fila['ultima_actividad_fecha'].isoformat() if fila['ultima_actividad_fecha'] else '',
            fila['ultima_actividad_etiqueta'],
            fila['ultima_actividad_precision'] or '',
        ])
    return response

def index(request):
    # Lógica para cargar el contenido del índice
    return render(request, 'index.html')
