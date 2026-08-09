import decimal
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from urllib.parse import urlencode

from cosecheros.forms import CosecheroForm, EntregaTabacoForm
from cosecheros.models import Cosecha, Cosechero, EntregaTabaco, PrecioVariedadCosecha
from cosecheros.services import (
    CLASIFICACIONES,
    calcular_produccion_entrega,
    calcular_resumenes_cosecha,
    clonar_precios,
    obtener_precios,
)

# Create your views here.

import io
from django.http import FileResponse
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,KeepTogether
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from ventas.models import Venta, DetalleArticulo, DetalleAvance
from ventas.services import obtener_detalles_venta, procesar_detalles_articulos
from reportlab.lib import pagesizes
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas


def encabezado_pie(canvas, doc):
    width, height = letter
    # Encabezado
    logo_width, logo_height = 160, 100
    canvas.drawImage("logo.png", width - logo_width - 72, height - 36 - logo_height, width=logo_width, height=logo_height, mask='auto')

    # Información de la empresa
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(width - 2*inch - 72, height - 36 - logo_height - 6, "Tabacalera Genao SRL")
    canvas.setFont("Helvetica", 9)
    canvas.drawString(width - 2*inch - 72, height - 36 - logo_height - 22, "RNC 131822096")
    canvas.drawString(width - 2*inch - 72, height - 36 - logo_height - 38, "C/3 #8 Villa Tabacalera")
    canvas.drawString(width - 2*inch - 72, height - 36 - logo_height - 54, "Navarrete, Santiago")
    canvas.drawString(width - 2*inch - 72, height - 36 - logo_height - 70, "Tel: 829-248-9996, 809-207-3871")

    # Información del cosechero
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(72, height - 36 - logo_height - 6, f"Nombre del Cosechero: {doc.cosechero_nombre}")
    canvas.setFont("Helvetica", 9)
    canvas.drawString(72, height - 36 - logo_height - 22, f"ID del Cosechero: {doc.cosechero_id}")
    canvas.drawString(72, height - 36 - logo_height - 38, f"Terreno sembrado: {doc.terreno} tareas")
    canvas.drawString(72, height - 36 - logo_height - 54, f"Direccion: {doc.direccion}")
    canvas.drawString(72, height - 36 - logo_height - 70, f"Tel: {doc.telefono}")

    # Pie de página
    canvas.drawString(inch, 0.75 * inch, f"Página {doc.page}")

def pie_pagina(canvas, doc):
    width, height = letter
    # Pie de página
    canvas.setFont("Helvetica", 9)
    canvas.drawString(inch, 0.75 * inch, f"Página {doc.page}")


def generar_tablas_entregas(cosechero, entregas, styles, usable_width, precios):
    """
    precios: dict {variedad: PrecioVariedadCosecha} de la cosecha, obtenido
    con cosecheros.services.obtener_precios() — una sola query para todo
    el reporte en vez de una tabla hardcodeada.
    """
    story = []
    total = decimal.Decimal('0')

    # Agrupar entregas por variedad
    entregas_agrupadas = {}
    for entrega in entregas:
        entregas_agrupadas.setdefault(entrega.variedad, []).append(entrega)

    # Iterar sobre cada variedad y sus entregas
    for variedad, entregas_variedad in entregas_agrupadas.items():
        story.append(Spacer(1, 12))
        story.append(Paragraph(f'Entregas de Tabaco - {variedad}', styles['Heading2']))

        precio_variedad = precios.get(variedad)
        if precio_variedad is None:
            story.append(Paragraph(
                f'⚠ No hay precios cargados para "{variedad}" en esta cosecha. '
                'Estas entregas no se valoraron (ir a Precios para completarlos).',
                styles['Normal']
            ))

        for entrega in entregas_variedad:
            story.append(Paragraph(f'{variedad} - {entrega.fecha_entrega.strftime("%d/%m/%Y")}', styles['Normal']))
            resultado = calcular_produccion_entrega(entrega, precio_variedad)
            data_entrega = [['Clasificación', 'Cantidad', 'Precio', 'Subtotal']]

            for linea in resultado['lineas']:
                data_entrega.append([
                    linea['clasificacion'],
                    f"{linea['cantidad_tara']:,.2f}",
                    f"${linea['precio']:,.2f}",
                    f"${linea['importe']:,.2f}",
                ])

            data_entrega.append(['Subtotal', '', '', f"${resultado['subtotal']:,.2f}"])

            tabla_entrega = Table(data_entrega, colWidths=[usable_width * 0.3, usable_width * 0.2, usable_width * 0.2, usable_width * 0.3])
            tabla_entrega.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12)
            ]))

            story.append(tabla_entrega)
            total += resultado['subtotal']  # Acumular el total de las entregas

    return total, story


@login_required
def generar_reporte_cosechero(request, cosechero_id,cosecha_id):
    cosechero = get_object_or_404(Cosechero, pk=cosechero_id)
    cosecha = get_object_or_404(Cosecha, pk=cosecha_id)

    ventas = Venta.objects.filter(cosechero_id=cosechero_id, cosecha=cosecha, is_active=True)
    resumenes = calcular_resumenes_cosecha(cosecha_id, cosechero_ids=[cosechero_id])
    resumen_financiero = resumenes[0] if resumenes else {
        'gastos_articulos': Decimal('0'),
        'gastos_avances': Decimal('0'),
        'gastos': Decimal('0'),
        'produccion': Decimal('0'),
        'saldo': Decimal('0'),
        'tareas_sembradas': cosechero.terreno_sembrado,
        'gasto_promedio_tarea': Decimal('0') if cosechero.terreno_sembrado > 0 else None,
        'produccion_promedio_tarea': Decimal('0') if cosechero.terreno_sembrado > 0 else None,
        'quintales_producidos': Decimal('0'),
        'quintales_promedio_tarea': Decimal('0') if cosechero.terreno_sembrado > 0 else None,
    }
    detalles_articulos = DetalleArticulo.objects.filter(venta__in=ventas).select_related('articulo').order_by('articulo__descripcion')

    articulos_agrupados = procesar_detalles_articulos(detalles_articulos)

    # Crear un archivo PDF en memoria
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=72, leftMargin=72, bottomMargin=72)
    story = []
    styles = getSampleStyleSheet()
    #doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=72, leftMargin=72, topMargin=100, bottomMargin=72)
    
    
    page_width, page_height = pagesizes.letter
    usable_width = page_width - 2 * 72  # Restar márgenes izquierdo y derecho

    # Definir los anchos de las columnas
    column_widths = [
        usable_width * 0.3,  # Artículo
        usable_width * 0.2,  # Presentación
        usable_width * 0.15, # Cantidad
        usable_width * 0.15, # Precio
        usable_width * 0.2   # Importe
    ]
    doc.cosechero_nombre = f'{cosechero.nombre} {cosechero.apellido}'
    doc.cosechero_id = cosechero_id
    doc.terreno = cosechero.terreno_sembrado
    doc.direccion = cosechero.direccion
    doc.telefono = cosechero.telefono


    story.append(Spacer(1, 140))
    story.append(Paragraph('Reporte de Cosechero', styles['Title']))
    
    
    story.append(Spacer(1, 12))

    story.append(Paragraph('Detalle de Artículos', styles['Heading2']))

    # Añadir detalles de las ventas
    data = [['Artículo', 'Presentación', 'Cantidad', 'Precio', 'Importe']]

    # Añadir filas a la tabla basadas en los artículos agrupados
    articulos_ordenados = sorted(articulos_agrupados, key=lambda x: x['descripcion'])
    for articulo in articulos_ordenados:
        data.append([
            articulo['descripcion'],
            articulo['presentacion'],
            articulo['cantidad_total'],
            f"${articulo['precio_venta_final']:.2f}",
            f"${articulo['importe_total']:,.2f}"
        ])
    subtotal_articulos = resumen_financiero['gastos_articulos']

    # Crear la tabla con los datos
    #data_ordenada = sorted(data, key=lambda x: x[0])
    tabla_articulos = Table(data, colWidths=column_widths)
    tabla_articulos.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12)
    ]))

    story.append(tabla_articulos)
    story.append(Spacer(1, 12))  # Espacio después de la tabla

    avances = DetalleAvance.objects.filter(venta__in=ventas).select_related('avance').order_by('avance__fecha')

# Preparar los datos para la tabla de avances

    data_avances = [['Tipo','Numero', 'Descripción', 'Fecha', 'Monto']]
    for avance in avances:
        data_avances.append([
            avance.avance.get_tipo_avance_display(),  # Suponiendo que `tipo_avance` es un campo con choices
            avance.avance.numero,
            avance.avance.descripcion,
            avance.avance.fecha.strftime("%d/%m/%Y"),
            f"${avance.monto:,.2f}"
        ])
    subtotal_avances = resumen_financiero['gastos_avances']

    tabla_avances = Table(data_avances, colWidths=[usable_width * 0.2, usable_width * 0.1 ,usable_width * 0.3, usable_width * 0.2, usable_width * 0.2])
    tabla_avances.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12)
    ]))

    story.append(Paragraph('Detalle de Avances', styles['Heading2']))
    story.append(Spacer(1, 12))
    story.append(tabla_avances)
    #story.append(Spacer(1, 12))

    entregas = EntregaTabaco.objects.filter(cosechero=cosechero,cosecha=cosecha).order_by('fecha_entrega')
    subtotal_entregas = resumen_financiero['produccion']
    if entregas.exists():
        precios = obtener_precios(cosecha)
        _, story_entregas = generar_tablas_entregas(cosechero, entregas, styles, usable_width, precios)
        story.extend(story_entregas)

    total_gasto = resumen_financiero['gastos']
    total = resumen_financiero['saldo']
    resumen_data = [
        ['Subtotal Artículos:', f"${subtotal_articulos:,.2f}"],
        ['Subtotal Avances:', f"${subtotal_avances:,.2f}"],
        ['Total Gasto:', f"${total_gasto:,.2f}"],
        ['Total Produccion:', f"${subtotal_entregas:,.2f}"],
        ['Tareas sembradas:', f"{resumen_financiero['tareas_sembradas']:,.2f}"],
        [
            'Gasto por tarea:',
            f"${resumen_financiero['gasto_promedio_tarea']:,.2f}"
            if resumen_financiero['gasto_promedio_tarea'] is not None else 'Sin tareas',
        ],
        [
            'Produccion por tarea:',
            f"${resumen_financiero['produccion_promedio_tarea']:,.2f}"
            if resumen_financiero['produccion_promedio_tarea'] is not None else 'Sin tareas',
        ],
        ['Quintales entregados:', f"{resumen_financiero['quintales_producidos']:,.2f} qq"],
        [
            'Quintales por tarea:',
            f"{resumen_financiero['quintales_promedio_tarea']:,.2f} qq"
            if resumen_financiero['quintales_promedio_tarea'] is not None else 'Sin tareas',
        ],
        ['Total Gastos  - Total Produccion:', f"${total:,.2f}"],
    ]
    tabla_resumen = Table(resumen_data, colWidths=[usable_width * 0.6, usable_width * 0.4])
    tabla_resumen.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
    ]))

    firma_data = [
        ['__________________________________', '', '__________________________________'],
        ['Firma Cosechero', '', 'Firma Representante'],
        [(f"{cosechero.nombre} {cosechero.apellido}"),'','Tabacalera Genao SRL']
    ]

    tabla_firma = Table(firma_data, colWidths=[usable_width * 0.4, usable_width * 0.2, usable_width * 0.4])
    tabla_firma.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
    ]))

    #story.append(Spacer(1, 50))
    story.append(KeepTogether([
        Paragraph('Resumen', styles['Heading2']),
        tabla_resumen,
        Spacer(1, 75),
        tabla_firma
    ]))




    # Generar PDF
    doc.build(story, onFirstPage=encabezado_pie, onLaterPages=pie_pagina)
    buffer.seek(0)
    return FileResponse(buffer, as_attachment=True, filename='reporte_cosechero_'+cosechero.__str__()+'_'+cosecha.__str__()+'.pdf')


@login_required
@require_GET
def show_cosechero(request, id):
    try:
        cosechero_data = Cosechero.objects.values().get(id=id)
        return JsonResponse(cosechero_data)
    except Cosechero.DoesNotExist:
        raise Http404("Cosechero no encontrado")


def _contexto_listado(request, form=None, modal_cosechero=None):
    """Construye el listado paginado y conserva los filtros de la pantalla."""
    cosechas = Cosecha.objects.all().order_by('-fecha_inicio')
    cosecha_default = cosechas.first()
    cosecha_id = request.GET.get('cosecha')

    if cosecha_id:
        cosecha_seleccionada = cosechas.filter(pk=cosecha_id).first()
    else:
        cosecha_seleccionada = cosecha_default

    busqueda = request.GET.get('q', '').strip()
    cosecheros = Cosechero.objects.filter(is_active=True).order_by('nombre', 'apellido')
    if busqueda:
        cosecheros = cosecheros.filter(
            Q(nombre__icontains=busqueda)
            | Q(apellido__icontains=busqueda)
            | Q(cedula__icontains=busqueda)
            | Q(telefono__icontains=busqueda)
        )

    page_obj = Paginator(cosecheros, 25).get_page(request.GET.get('page'))

    if form is None:
        initial = {'cosecha': cosecha_seleccionada.id} if cosecha_seleccionada else {}
        form = EntregaTabacoForm(initial=initial)

    return {
        'form': form,
        'page_obj': page_obj,
        'cosecheros': page_obj.object_list,
        'cosechas': cosechas,
        'cosecha_default': cosecha_default,
        'cosecha_seleccionada': cosecha_seleccionada,
        'busqueda': busqueda,
        'modal_cosechero': modal_cosechero,
    }


@login_required
@require_GET
def index(request):
    return render(request, 'index.html', _contexto_listado(request))


@login_required
def guardar_cosechero(request, cosechero_id=None):
    cosechero = get_object_or_404(Cosechero, pk=cosechero_id, is_active=True) if cosechero_id else None
    form = CosecheroForm(request.POST or None, instance=cosechero)
    if request.method == 'POST' and form.is_valid():
        objeto = form.save()
        messages.success(request, f'Cosechero {objeto} guardado correctamente.')
        return redirect('cosecheros')
    return render(request, 'crud_form.html', {
        'form': form,
        'titulo': 'Editar cosechero' if cosechero else 'Nuevo cosechero',
        'volver_url': reverse('cosecheros'),
    }, status=400 if request.method == 'POST' else 200)


@login_required
@require_POST
def eliminar_cosechero(request, cosechero_id):
    cosechero = get_object_or_404(Cosechero, pk=cosechero_id, is_active=True)
    cosechero.delete()
    messages.success(request, f'{cosechero} fue desactivado.')
    return redirect('cosecheros')


@login_required
@require_POST
def alta_rapida_cosechero(request):
    form = CosecheroForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'success': False, 'errors': form.errors.get_json_data()}, status=400)
    cosechero = form.save()
    return JsonResponse({
        'success': True,
        'object': {'id': cosechero.id, 'nombre': str(cosechero)},
    }, status=201)


@login_required
@require_POST
def agregar_entrega_tabaco(request, cosechero_id):
    cosechero = get_object_or_404(Cosechero, pk=cosechero_id, is_active=True)
    form = EntregaTabacoForm(request.POST)

    if form.is_valid():
        entrega = form.save(commit=False)
        entrega.cosechero = cosechero
        entrega.save()
        messages.success(
            request,
            f'Entrega registrada correctamente para {cosechero}.',
        )
        filtros = {
            key: request.GET.get(key)
            for key in ('q', 'page', 'cosecha')
            if request.GET.get(key)
        }
        destino = reverse('cosecheros')
        if filtros:
            destino = f'{destino}?{urlencode(filtros)}'
        return redirect(destino)

    messages.error(request, 'Revise los campos marcados en la entrega.')
    contexto = _contexto_listado(request, form=form, modal_cosechero=cosechero)
    return render(request, 'index.html', contexto, status=400)


# ─────────────────────────────────────────────
# Gestión de precios por variedad/cosecha
# ─────────────────────────────────────────────

@login_required
def gestionar_precios(request):
    """
    Hoja de precios (formato ancho: 1 fila por variedad, 7 columnas de
    clasificación) para la cosecha seleccionada. Reemplaza la tabla de
    precios hardcodeada que antes vivía en el código del reporte.
    """
    cosechas = Cosecha.objects.all().order_by('-fecha_inicio')
    cosecha_id = request.POST.get('cosecha') or request.GET.get('cosecha')
    cosecha_actual = get_object_or_404(Cosecha, pk=cosecha_id) if cosecha_id else cosechas.first()

    if request.method == 'POST' and cosecha_actual is not None:
        accion = request.POST.get('accion', 'guardar')

        if accion == 'clonar':
            origen_id = request.POST.get('origen_cosecha')
            if origen_id:
                origen = get_object_or_404(Cosecha, pk=origen_id)
                creadas = clonar_precios(origen, cosecha_actual)
                if creadas:
                    messages.success(request, f'Se copiaron {creadas} precio(s) desde "{origen}".')
                else:
                    messages.info(
                        request,
                        f'"{cosecha_actual}" ya tenía todos los precios de "{origen}" '
                        '(no se sobreescribió nada).'
                    )
        else:
            # Guardar: recorre las variedades en el mismo orden fijo con el
            # que se renderizaron (EntregaTabaco.VARIEDADES_CHOICES), sin
            # depender de campos ocultos que el navegador pudiera alterar.
            for idx, (variedad_code, _) in enumerate(EntregaTabaco.VARIEDADES_CHOICES):
                valores = {}
                for _, _, campo, _ in CLASIFICACIONES:
                    valor = request.POST.get(f'precio-{idx}-{campo}', '').strip()
                    valores[campo] = Decimal(valor) if valor else Decimal('0')
                PrecioVariedadCosecha.objects.update_or_create(
                    cosecha=cosecha_actual, variedad=variedad_code, defaults=valores
                )
            messages.success(request, f'Precios de "{cosecha_actual}" guardados.')

        return redirect(f"{reverse('precios')}?cosecha={cosecha_actual.id}")

    precios_map = obtener_precios(cosecha_actual) if cosecha_actual else {}
    columnas = [etiqueta for etiqueta, _, _, _ in CLASIFICACIONES]

    filas = []
    for variedad_code, variedad_label in EntregaTabaco.VARIEDADES_CHOICES:
        precio = precios_map.get(variedad_code)
        valores = [
            (campo, getattr(precio, campo) if precio else Decimal('0'))
            for _, _, campo, _ in CLASIFICACIONES
        ]
        filas.append({'variedad': variedad_code, 'etiqueta': variedad_label, 'valores': valores})

    context = {
        'cosechas': cosechas,
        'cosecha_actual': cosecha_actual,
        'columnas': columnas,
        'filas': filas,
    }
    return render(request, 'precios.html', context)
