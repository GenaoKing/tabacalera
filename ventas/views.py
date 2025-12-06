from decimal import Decimal
import decimal
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.forms import inlineformset_factory

from compra.models import DetalleCompra
from compra.views import calcular_inventario
from .forms import VentaForm, DetalleArticuloForm, DetalleAvanceForm
from .models import Venta, DetalleArticulo, DetalleAvance, Avance, Cosechero
from django.db import transaction
from cosecheros.models import Cosechero
from articulo.models import Articulo
from django.core import serializers
import json
from escpos.printer import Usb
from PIL import Image
from django.core.serializers.json import DjangoJSONEncoder
from datetime import datetime, timedelta
from django.utils.timezone import now
from itertools import groupby
from operator import itemgetter


# Reemplaza 0xXXXX con tu VID y PID respectivamente
VID = 0x1FC9
PID = 0x2016
logo = Image.open("logo.png")



def proximo_sabado(fecha_venta):
    dias_hasta_sabado = (5 - fecha_venta.weekday()) % 7  # 5 representa el sábado
    if dias_hasta_sabado == 0:
        return fecha_venta  # Si la venta es un sábado, se devuelve la misma fecha
    return fecha_venta + timedelta(days=dias_hasta_sabado)



def obtener_venta_existente(cosechero_id, fecha_sabado):
    inicio_semana = fecha_sabado - timedelta(days=fecha_sabado.weekday())
    fin_semana = inicio_semana + timedelta(days=6)
    ventas = Venta.objects.filter(cosechero_id=cosechero_id, fecha_venta__range=(inicio_semana, fin_semana))
    return ventas.first() if ventas.exists() else None


def obtener_lotes_para_venta(articulo_id, cantidad_solicitada):
    lotes_seleccionados = []
    cantidad_restante = decimal.Decimal(cantidad_solicitada)

    # Obtener los detalles de compra ordenados por fecha de compra
    detalles_compra = DetalleCompra.objects.filter(
        articulo_id=articulo_id, 
        cantidad_restante__gt=0, 
        compra__is_active=True,
        is_active=True
    ).order_by('compra__fecha_compra')

    for detalle in detalles_compra:
        if cantidad_restante <= 0:
            break

        cantidad_disponible = detalle.cantidad_restante
        if cantidad_disponible <= cantidad_restante:
            lotes_seleccionados.append({'compra_id': detalle.compra_id, 'cantidad': cantidad_disponible, 'precio_venta': detalle.precio_venta_sugerido})
            detalle.cantidad_restante = 0  # Actualizar la cantidad restante en el lote
            cantidad_restante -= cantidad_disponible
        else:
            lotes_seleccionados.append({'compra_id': detalle.compra_id, 'cantidad': cantidad_restante, 'precio_venta': detalle.precio_venta_sugerido})
            detalle.cantidad_restante -= cantidad_restante  # Actualizar la cantidad restante en el lote
            cantidad_restante = 0

        detalle.save()  # Guardar los cambios en el lote

    return lotes_seleccionados


def calcular_inventario_y_precio_ventaj(articulos):
    articulos_con_inventario = []
    for articulo in articulos:
        detalle_compras = DetalleCompra.objects.filter(
            articulo_id=articulo.id,
            is_active=True
        ).order_by('compra__fecha_compra')

        total_inventario = sum(detalle.cantidad_restante for detalle in detalle_compras)

        # Obtener el precio de venta del lote más antiguo
        if detalle_compras.exists() and total_inventario > 0:
            lote_mas_antiguo = detalle_compras.first()
            precio_venta_lote_mas_antiguo = lote_mas_antiguo.precio_venta_sugerido
        else:
            precio_venta_lote_mas_antiguo = 0

        articulo_dict = {
            'id': articulo.id,
            'descripcion': articulo.descripcion,
            'categoria': articulo.categoria,
            'presentacion': articulo.presentacion,
            'cantidad_minima_orden': articulo.cantidad_minima_orden,
            'proveedor': articulo.proveedor_id,
            'is_active': articulo.is_active,
            'inventario': total_inventario,
            'precio_venta': float(precio_venta_lote_mas_antiguo)
        }
        articulos_con_inventario.append(articulo_dict)

    return articulos_con_inventario


def calcular_inventario_y_precio_venta(articulos):
    for articulo in articulos:
        detalle_compras = DetalleCompra.objects.filter(
            articulo_id=articulo.id,
            is_active=True
        ).order_by('compra__fecha_compra')

        total_inventario = sum(detalle.cantidad_restante for detalle in detalle_compras)

        # Obtener el precio de venta del lote más antiguo
        if detalle_compras.exists() and total_inventario > 0:
            lote_mas_antiguo = detalle_compras.first()
            precio_venta_lote_mas_antiguo = lote_mas_antiguo.precio_venta_sugerido
        else:
            precio_venta_lote_mas_antiguo = 0

        articulo.inventario = total_inventario
        articulo.precio_venta = float(precio_venta_lote_mas_antiguo)

    return articulos

def crear_avances(request_post, venta, mutable_post):
    total_avances = int(mutable_post.get('detalle_avances-TOTAL_FORMS'))
    for i in range(total_avances):
        descripcion = request_post.get(f'detalle_avances-{i}-descripcion')
        tipo_avance = request_post.get(f'detalle_avances-{i}-tipo_avance')
        numero = request_post.get(f'detalle_avances-{i}-numero')
        monto = request_post.get(f'detalle_avances-{i}-monto')
        estado = request_post.get(f'detalle_avances-{i}-estado')
        fecha = request_post.get(f'detalle_avances-{i}-fecha')

        if descripcion and tipo_avance and numero and monto:
            avance = Avance.objects.create(
                descripcion=descripcion,
                tipo_avance=tipo_avance,
                numero=numero,
                monto_pagado=monto,
                cosechero=venta.cosechero,
                estado=estado,
                fecha=fecha
            )
            avance.save()
            mutable_post[f'detalle_avances-{i}-avance'] = avance.id

def actualizar_inventario(request_post):
    total_formularios = int(request_post.get('detalle_articulos-TOTAL_FORMS'))
    for i in range(1, total_formularios + 1):
        articulo_id = request_post.get(f'detalle_articulos-{i}-articulo')
        cantidad_vendida = request_post.get(f'detalle_articulos-{i}-cantidad')

        if articulo_id and cantidad_vendida:
            obtener_lotes_para_venta(articulo_id, cantidad_vendida)


def actualizar_inventario_y_crear_detalles(venta, request_post):
    total_formularios = int(request_post.get('detalle_articulos-TOTAL_FORMS'))
    for i in range(total_formularios):
        articulo_id = request_post.get(f'detalle_articulos-{i}-articulo')
        cantidad_vendida = request_post.get(f'detalle_articulos-{i}-cantidad')

        if articulo_id and cantidad_vendida:
            lotes_para_venta = obtener_lotes_para_venta(articulo_id, cantidad_vendida)
            for lote in lotes_para_venta:
                DetalleArticulo.objects.create(
                    venta=venta,
                    articulo_id=articulo_id,
                    cantidad=lote['cantidad'],
                    precio_venta_final=lote['precio_venta']
                )



def view_imprimir(request,venta_id):
    venta = get_object_or_404(Venta, pk=venta_id)
    imprimir(request,venta)
    return HttpResponse("Impresión realizada para la venta #" + str(venta_id))


def imprimir(request,venta):
    try:
        p = Usb(idVendor=VID, idProduct=PID)

        # Imprimir el nombre de la empresa
        
        
        p.set(align='center', bold=True)
        p.image(logo)
        p.text("Tabacalera Genao S.R.L\n")

        # Imprimir "Venta ID:" en negrita y luego el ID de la venta en normal
        p.set(align='left', bold=True)
        p.text("Venta ID: ")
        p.set(bold=False)
        p.text(f"{venta.id}             ")

        # Imprimir "Vendedor:" en negrita y luego el nombre del vendedor en normal
        p.set(bold=True)
        p.text("Vendedor: ")
        p.set(bold=False)
        p.text(f"{request.user.username}\n")

        # Similar para "Cosechero:" y "Fecha:"
        p.set(bold=True)
        p.text("Cosechero: ")
        p.set(bold=False)
        p.text(f"{venta.cosechero.nombre} {venta.cosechero.apellido}\n")

        p.set(bold=True)
        p.text("Fecha: ")
        p.set(bold=False)
        p.text(f"{venta.fecha_venta.strftime('%d/%m/%Y')}\n")


        if(len(venta.detalle_articulos.all()) > 0):
            # Imprimir los detalles de los artículos
            p.set(bold=True)
            p.text("\nDetalles de Artículos:\n")
            # Ejemplo de cómo imprimir detalles en formato de tabla
            p.text("Artículo              Cant.   Precio    Subtotal\n")
            p.text("------------------------------------------------\n")
            p.set(bold=False)
            detalles_venta = [
            {
                'articulo': detalle.articulo,
                'cantidad': detalle.cantidad,
                'precio_venta_final': detalle.precio_venta_final
            }
            for detalle in venta.detalle_articulos.all()
                
                ]
            print(detalles_venta)    
    # Ordenar los detalles por artículo y precio para asegurar una agrupación correcta

            # Agrupar los detalles por artículo y precio
            # Ordenar los detalles por artículo y precio para asegurar una agrupación correcta
            detalles_venta.sort(key=lambda x: (x['articulo'].id, x['precio_venta_final']))

            # Agrupar los detalles por ID de artículo y precio
            agrupados = []
            for key, group in groupby(detalles_venta, key=lambda x: (x['articulo'].id, x['precio_venta_final'])):
                # Convertir el grupo en una lista para evitar consumir el iterador
                group_list = list(group)
                # Ahora el objeto artículo y el precio se pueden obtener del primer elemento del grupo listo
                agrupados.append({
                    'articulo': group_list[0]['articulo'],
                    'precio_venta_final': key[1],
                    'cantidad_total': sum(item['cantidad'] for item in group_list)
                })



            print(agrupados)
            for detalle in agrupados:
                descripcion_completa = f"{detalle['articulo'].presentacion} {detalle['articulo'].descripcion}"
                p.text(f"{descripcion_completa[:19]:19} {detalle['cantidad_total']:5}     {detalle['precio_venta_final']:5.2f}   {detalle['cantidad_total'] * detalle['precio_venta_final']:7.2f}\n")

        if(len(venta.detalle_avances.all()) > 0):
            p.set(bold=True)
            p.text("\nDetalles de Avances:\n")
            p.text("Tipo      Descripcion         Fecha     Monto\n")
            p.text("------------------------------------------------\n")
            p.set(bold=False)
            for detalle in venta.detalle_avances.all():
                p.text(f"{detalle.avance.tipo_avance:8}  {detalle.avance.descripcion:15} {detalle.avance.fecha.strftime('%d/%m/%Y')} {detalle.monto}\n")

        # Imprimir el total
        p.set(bold=True, align='center', double_height=True, double_width=True)
        p.text(f"\nTotal: {venta.total}\n")

        # Cortar el papel
        # ... código anterior ...

        # Sección para la firma
        p.set(align='left', bold=False, double_height=False, double_width=False)
        p.text("\n\nRecibido por:\n\n")
        p.text("_____________________________________________\n")  # Línea para la firma
    

        # Espacio para el sello de la empresa
    
        p.ln(count=15) # Espacios en blanco

        # Cortar el papel
        p.cut() 
        p.close()
        venta.impreso = True

    except Exception as e:
        print(f"Error al imprimir: {e}")




def detalles_venta(request,venta_id):
    venta = get_object_or_404(Venta, pk=venta_id)
    detalles_articulos = DetalleArticulo.objects.filter(venta=venta).select_related('articulo')

    # Procesar detalles de artículos
    agrupados = procesar_detalles_articulos(detalles_articulos)

    # Obtener y procesar avances asociados
    avances = DetalleAvance.objects.filter(venta=venta).select_related('avance')
    avances_procesados = [
        {
            'descripcion': avance.avance.descripcion,
            'monto_pagado': float(avance.avance.monto_pagado),
            'numero': avance.avance.numero,
            'tipo': avance.avance.tipo_avance
        }
        for avance in avances
    ]

    data = {
        'cosechero_nombre': venta.cosechero.nombre+' '+venta.cosechero.apellido,
        'fecha_venta': venta.fecha_venta.strftime('%Y-%m-%d'),
        'total': float(venta.total),
        'detalles': agrupados,
        'avances': avances_procesados
    }

    return JsonResponse(data)

def procesar_detalles_articulos(detalles_articulos):
    # Preparar la lista de artículos incluyendo la presentación
    articulos_procesados = [
        {
            'articulo_id': detalle.articulo.id,
            'descripcion': detalle.articulo.descripcion,
            'presentacion': detalle.articulo.presentacion,
            'cantidad': detalle.cantidad,
            'precio_venta_final': float(detalle.precio_venta_final),
            'importe': detalle.cantidad * float(detalle.precio_venta_final)
        }
        for detalle in detalles_articulos
    ]

    # Ordenar los artículos para asegurar el agrupamiento correcto
    articulos_procesados.sort(key=lambda x: (x['articulo_id'], x['presentacion'], x['precio_venta_final'],x['descripcion']))

    # Agrupar los artículos por ID, presentación y precio
    agrupados = []
    for key, group in groupby(articulos_procesados, key=lambda x: (x['articulo_id'], x['presentacion'], x['precio_venta_final'],x['descripcion'])):
        group_list = list(group)
        agrupados.append({
            'descripcion': group_list[0]['descripcion'],
            'presentacion': group_list[0]['presentacion'],
            'cantidad_total': sum(item['cantidad'] for item in group_list),
            'precio_venta_final': key[2],
            'importe_total': sum(item['importe'] for item in group_list)
        })
    return agrupados






def get_tickets(request):
    ventas = Venta.objects.select_related('cosechero').all()
    return render(request, 'tickets.html', {'ventas': ventas})



def registrar_venta(request):
    DetalleArticuloFormSet = inlineformset_factory(Venta, DetalleArticulo, form=DetalleArticuloForm, extra=1)
    DetalleAvanceFormSet = inlineformset_factory(Venta, DetalleAvance, form=DetalleAvanceForm, extra=1)
    
    if request.method == 'POST':
        venta_form = VentaForm(request.POST)

        if venta_form.is_valid():
            with transaction.atomic():
                fecha_venta = venta_form.cleaned_data['fecha_venta']
                fecha_sabado = proximo_sabado(fecha_venta)
                cosechero_id = venta_form.cleaned_data['cosechero'].id
                if 'guardar_venta' in request.POST:
                    if obtener_venta_existente(cosechero_id, fecha_sabado) == None:
                        venta = venta_form.save(commit=False)
                        venta.fecha_venta = fecha_sabado
                        venta.impreso = False
                        total_venta = request.POST.get('total_venta')
                        venta.total = total_venta
                        venta.save()
                        mutable_post = request.POST.copy()
                        crear_avances(request.POST,venta,mutable_post)
                        detalle_articulo_formset = DetalleArticuloFormSet(request.POST, instance=venta)
                        detalle_avance_formset = DetalleAvanceFormSet(mutable_post, instance=venta)

                        if detalle_articulo_formset.is_valid():
                            for form in detalle_articulo_formset:
                                if form.cleaned_data and not form in detalle_articulo_formset.deleted_forms:
                                    articulo = form.cleaned_data['articulo']
                                    cantidad_vendida = form.cleaned_data['cantidad']
                                    if calcular_inventario(articulo.id) < cantidad_vendida:
                                        form.add_error('cantidad', 'No hay suficiente inventario')
                                        return render(request, 'ventas_form.html', {'venta_form': venta_form})

                        #actualizar_inventario(request.POST)
                        actualizar_inventario_y_crear_detalles(venta,request.POST)
                           
                                    
                        if detalle_avance_formset.is_valid(): 
                                detalle_avance_formset.save() 

                        venta_form = VentaForm()
                        detalle_articulo_formset = DetalleArticuloFormSet()
                        detalle_avance_formset = DetalleAvanceFormSet()
                        articulos = Articulo.objects.all()
                        inventario_precio_venta = calcular_inventario_y_precio_venta(articulos)

                    else:
                        # Agregar artículos y avances a la venta existente
                        venta_existente = obtener_venta_existente(cosechero_id, fecha_sabado)

                        total_venta = request.POST.get('total_venta')
                        venta_existente.total += Decimal(total_venta)
                        venta_existente.save()
                        
                        mutable_post = request.POST.copy()
                        detalle_articulo_formset = DetalleArticuloFormSet(request.POST, instance=venta_existente)
                        detalle_avance_formset = DetalleAvanceFormSet(mutable_post, instance=venta_existente)
                        
                        
                    # Procesar datos para Avance y actualizar el QueryDict para DetalleAvance
                        crear_avances(request.POST,venta_existente,mutable_post)
                        
                        #actualizar_inventario(request.POST)
                        actualizar_inventario_y_crear_detalles(venta_existente,request.POST)
                        

                        if detalle_avance_formset.is_valid():
                            detalle_avance_formset.save()

                        venta_form = VentaForm()
                        detalle_articulo_formset = DetalleArticuloFormSet()
                        detalle_avance_formset = DetalleAvanceFormSet()
                        articulos = Articulo.objects.all()
                        inventario_precio_venta = calcular_inventario_y_precio_venta(articulos)
                       
                
                elif obtener_venta_existente(cosechero_id, fecha_sabado) == None:
                    fecha_venta = venta_form.cleaned_data['fecha_venta']
                    fecha_sabado = proximo_sabado(fecha_venta)
                    venta = venta_form.save(commit=False)
                    venta.fecha_venta = fecha_sabado
                    total_venta = request.POST.get('total_venta')
                    venta.total = total_venta 
                    venta.impreso = True # Asegúrate de convertir a Decimal si es necesario
                    venta.save()  # Guarda la instancia de Venta
                    print(request.POST)

                    mutable_post = request.POST.copy()
                    # Procesar datos para Avance y actualizar el QueryDict para DetalleAvance
                    
                    crear_avances(request.POST,venta,mutable_post)
                    #actualizar_inventario(request.POST)
                    actualizar_inventario_y_crear_detalles(venta,request.POST)
                    detalle_articulo_formset = DetalleArticuloFormSet(request.POST, instance=venta)
                    detalle_avance_formset = DetalleAvanceFormSet(mutable_post, instance=venta)
                    if detalle_articulo_formset.is_valid():
                        for form in detalle_articulo_formset:
                            if form.cleaned_data and not form in detalle_articulo_formset.deleted_forms:
                                articulo = form.cleaned_data['articulo']
                                cantidad_vendida = form.cleaned_data['cantidad']
                                if calcular_inventario(articulo.id) < cantidad_vendida:
                                    form.add_error('cantidad', 'No hay suficiente inventario')
                                    return render(request, 'ventas_form.html', {'venta_form': venta_form})

                        # Guardar el formset
                       

                        # Actualizar el inventari
                        
                                
                    if detalle_avance_formset.is_valid(): 
                            detalle_avance_formset.save() 
                    venta.save()
                    imprimir(request,venta)
                    # Conectar con la impresora
                else :
                    venta_existente = obtener_venta_existente(cosechero_id, fecha_sabado)
                    venta_existente.impreso = True
                    total_venta = request.POST.get('total_venta')
                    venta_existente.total += Decimal(total_venta)
                    venta_existente.save()
                    
                    mutable_post = request.POST.copy()
                    detalle_articulo_formset = DetalleArticuloFormSet(request.POST, instance=venta_existente)
                    detalle_avance_formset = DetalleAvanceFormSet(mutable_post, instance=venta_existente)
                    
                    
                # Procesar datos para Avance y actualizar el QueryDict para DetalleAvance
                    print(request.POST)
                    crear_avances(request.POST,venta_existente,mutable_post)
                    
                    #actualizar_inventario(request.POST)
                    actualizar_inventario_y_crear_detalles(venta_existente,request.POST)
                    

                    if detalle_avance_formset.is_valid():
                        detalle_avance_formset.save()
                
                    venta_existente.save()
                    imprimir(request,venta_existente)
                return redirect('/ventas')         
    else:
        venta_form = VentaForm()
        detalle_articulo_formset = DetalleArticuloFormSet()
        detalle_avance_formset = DetalleAvanceFormSet()
        articulos = Articulo.objects.all()
        inventario_precio_venta = calcular_inventario_y_precio_venta(articulos)
        

    context = {
        # En tu vista de Django
        'cosecheros' : Cosechero.objects.all().order_by('nombre', 'apellido'),        
        'articulos_json':  json.dumps(calcular_inventario_y_precio_ventaj(Articulo.objects.all()), cls=DjangoJSONEncoder),
        'articulos': inventario_precio_venta,
        'venta_form': venta_form,
        'detalle_articulo_formset': detalle_articulo_formset,
        'detalle_avance_formset': detalle_avance_formset,
        
    }
    
    return render(request, 'ventas_form.html', context)
