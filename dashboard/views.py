import csv
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

from cosecheros.models import Cosecha
from cosecheros.services import calcular_saldos_cosecha

@login_required
def dashboard(request):
    cosechas = Cosecha.objects.all().order_by('-fecha_inicio')
    cosecha_id = request.GET.get('cosecha')
    cosecha = get_object_or_404(Cosecha, pk=cosecha_id) if cosecha_id else cosechas.first()
    saldos = calcular_saldos_cosecha(cosecha.id) if cosecha else []
    q = request.GET.get('q', '').strip().lower()
    if q:
        saldos = [fila for fila in saldos if q in str(fila['cosechero']).lower()]

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
        'nos_deben': nos_deben,
        'les_debemos': les_debemos,
        'total_nos_deben': total_nos_deben,
        'total_les_debemos': total_les_debemos,
        'balance_neto': total_nos_deben - total_les_debemos,
    }
    return render(request, 'dashboard/dashboard.html', context)


@login_required
def exportar_csv(request):
    cosecha = get_object_or_404(Cosecha, pk=request.GET.get('cosecha'))
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="saldos_{cosecha.id}.csv"'
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow(['Cosechero', 'Gastos', 'Producción', 'Saldo', 'Estado'])
    for fila in calcular_saldos_cosecha(cosecha.id):
        writer.writerow([
            str(fila['cosechero']), fila['gastos'], fila['produccion'], fila['saldo'],
            'Nos debe' if fila['saldo'] > 0 else 'Le debemos' if fila['saldo'] < 0 else 'Saldado',
        ])
    return response

def index(request):
    # Lógica para cargar el contenido del índice
    return render(request, 'index.html')
