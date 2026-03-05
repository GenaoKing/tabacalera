# cosecheros/views.py
import decimal
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from cosecheros.forms import EntregaTabacoForm
from cosecheros.models import Cosecha, Cosechero, EntregaTabaco

# Create your views here.

import io
from django.http import FileResponse
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,KeepTogether
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from ventas.models import Venta, DetalleArticulo, DetalleAvance
from ventas.views import procesar_detalles_articulos
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


def aplicar_tara(cantidad, clasificacion):
    parte_entera = int(cantidad)
    parte_decimal = cantidad - parte_entera
    if clasificacion in ['Centro Largo', 'Centro Corto', 'Uno y Medio', 'Libre Pie']:
        parte_decimal *= decimal.Decimal(1.80)
    elif clasificacion in ['Criollo', 'Rezago', 'Picadura']:
        parte_decimal *= decimal.Decimal(1.60)
    return parte_entera + parte_decimal



def generar_tablas_entregas(cosechero, entregas, styles, usable_width):
    story = []
    total = 0

    # Agrupar entregas por variedad
    entregas_agrupadas = {}
    for entrega in entregas:
        if entrega.variedad not in entregas_agrupadas:
            entregas_agrupadas[entrega.variedad] = []
        entregas_agrupadas[entrega.variedad].append(entrega)

    # Iterar sobre cada variedad y sus entregas
    for variedad, entregas_variedad in entregas_agrupadas.items():
        story.append(Spacer(1, 12))
        story.append(Paragraph(f'Entregas de Tabaco - {variedad}', styles['Heading2']))

        for entrega in entregas_variedad:
            story.append(Paragraph(f'{variedad} - {entrega.fecha_entrega.strftime("%d/%m/%Y")}', styles['Normal']))
            data_entrega = [['Clasificación', 'Cantidad', 'Precio', 'Subtotal']]
            subtotal_entrega = 0

            clasificaciones = [
                ('Centro Largo', entrega.centro_largo),
                ('Centro Corto', entrega.centro_corto),
                ('Uno y Medio', entrega.uno_medio),
                ('Libre Pie', entrega.libre_pie),
                ('Picadura', entrega.picadura),
                ('Rezago', entrega.rezago),
                ('Criollo', entrega.criollo),
            ]

            precios = {
                'Corojo Original': [12000, 12000, 9000, 4000, 3000, 3000, 2500],
                'Corojo 99': [12000, 12000, 9000, 4500, 3000, 3000, 2500],
                'Habano 92': [12000, 12000, 9000, 4500, 3000, 3000, 2500],
                'Criollo 98': [12000, 12000, 9000, 4500, 3000, 3000, 2500],
                'Piloto Mejorado': [12000, 12000, 9000, 4500, 3000, 3000, 2500],
                'HVA': [12000, 12000, 9000, 4500, 3000, 3000, 2500],
            }

            precios_variedad = precios[variedad]

            for (clasificacion, cantidad), precio in zip(clasificaciones, precios_variedad):
                if cantidad > 0:
                    cantidad_tara = aplicar_tara(cantidad, clasificacion)
                    subtotal = cantidad_tara * precio
                    subtotal_entrega += subtotal
                    data_entrega.append([clasificacion, f"{cantidad_tara:,.2f}", f"${precio:,.2f}", f"${subtotal:,.2f}"])

            data_entrega.append(['Subtotal', '', '', f"${subtotal_entrega:,.2f}"])

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
            total += subtotal_entrega  # Acumular el total de las entregas

    return total,story


def generar_reporte_cosechero(request, cosechero_id,cosecha_id):
    cosechero = Cosechero.objects.get(pk=cosechero_id)
    cosecha = get_object_or_404(Cosecha, pk=cosecha_id)
    
    print(request.POST)
    ventas = Venta.objects.filter(cosechero_id=cosechero_id, cosecha=cosecha)
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
    subtotal_articulos = 0
    articulos_ordenados = sorted(articulos_agrupados, key=lambda x: x['descripcion'])
    for articulo in articulos_ordenados:
        data.append([
            articulo['descripcion'],
            articulo['presentacion'],
            articulo['cantidad_total'],
            f"${articulo['precio_venta_final']:.2f}",
            f"${articulo['importe_total']:,.2f}"
        ])
        subtotal_articulos+=articulo['importe_total']

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

    subtotal_avances = 0
    data_avances = [['Tipo','Numero', 'Descripción', 'Fecha', 'Monto']]
    for avance in avances:
        data_avances.append([
            avance.avance.get_tipo_avance_display(),  # Suponiendo que `tipo_avance` es un campo con choices
            avance.avance.numero,
            avance.avance.descripcion,
            avance.avance.fecha.strftime("%d/%m/%Y"),
            f"${avance.avance.monto_pagado:,.2f}"
        ])
        subtotal_avances+=avance.avance.monto_pagado

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
    subtotal_entregas = decimal.Decimal(0.0)
    if len(entregas) > 0:

        subtotal_entregas,story_entregas=generar_tablas_entregas(cosechero,entregas, styles, usable_width)
        story.extend(story_entregas)
   

    total_gasto = float(subtotal_articulos) + float(subtotal_avances)
    total = decimal.Decimal(total_gasto) - subtotal_entregas
    resumen_data = [
        ['Subtotal Artículos:', f"${subtotal_articulos:,.2f}"],
        ['Subtotal Avances:', f"${subtotal_avances:,.2f}"],
        ['Total Gasto:', f"${total_gasto:,.2f}"],
        ['Total Produccion:', f"${subtotal_entregas:,.2f}"],
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


def show_cosechero(request, id):
    try:
        cosechero_data = Cosechero.objects.values().get(id=id)
        return JsonResponse(cosechero_data)
    except Cosechero.DoesNotExist:
        raise Http404("Cosechero no encontrado")
    
def index(request):
    form = EntregaTabacoForm(request.POST or None)
    cosecheros = Cosechero.objects.all()
    cosechas = Cosecha.objects.all().order_by('-fecha_inicio')
    cosecha_default = cosechas.first()  # Select the most recent harvest
    initial = {'cosecha': cosecha_default.id} if cosecha_default else {}
    form = EntregaTabacoForm(initial=initial)
    return render(request, "index.html", {'cosecheros': cosecheros, 'cosechas': cosechas, 'cosecha_default': cosecha_default, 'form': form,})

def agregar_entrega_tabaco(request, cosechero_id):
    cosechero = get_object_or_404(Cosechero, pk=cosechero_id)
    if request.method == 'POST':
        form = EntregaTabacoForm(request.POST)
        if form.is_valid():
            entrega = form.save(commit=False)
            entrega.cosechero = cosechero
            entrega.save()
            return redirect('cosecheros')  # Cambia 'index' por el nombre correcto de tu vista de listado de cosecheros
    else:
        form = EntregaTabacoForm()
        cosecheros = Cosechero.objects.all()
        cosechas = Cosecha.objects.all().order_by('-fecha_inicio')
        cosecha_default = cosechas.first()  # Select the most recent harvest
        initial = {'cosecha': cosecha_default.id} if cosecha_default else {}
        form = EntregaTabacoForm(initial=initial)
        return render(request, "index.html", {'cosecheros': cosecheros, 'cosechas': cosechas, 'cosecha_default': cosecha_default, 'form': form,})