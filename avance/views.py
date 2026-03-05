# avance/views.py
from datetime import date, datetime
from pathlib import Path
import re
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils.dateparse import parse_date
from avance.models import Avance
from ventas.views import *
from ventas.models import *
from cosecheros.models import Cosechero
from .forms import FileUploadForm
import pandas as pd
import os
from django.views.decorators.http import require_http_methods
from io import StringIO

import re
ID_NO_COSECHERO = 30002  # Usuario de descargo (cheques que NO son de cosecheros)
from decimal import Decimal


def limpiar_cuenta(valor):
    if pd.isna(valor):
        return None
    s = str(valor).strip()
    # Deja solo dígitos (elimina -, espacios, puntos, etc.)
    s = re.sub(r'\D+', '', s)
    return s or None


def parse_fecha_from_filename(fname: str):
    name = Path(fname).stem
    m = re.search(r'\b(\d{2})-(\d{2})-(\d{2})\b', name)  # mm-dd-yy
    if not m:
        return None
    return datetime.strptime(m.group(0), '%m-%d-%y').date()



def parse_fecha_cell_ddmmyyyy(txt: str):
    # Normaliza d/m/YYYY o dd/m/YYYY a dd/mm/YYYY y parsea
    s = str(txt).strip()
    if not s:
        return None
    parts = s.split('/')
    if len(parts) != 3:
        raise ValueError(f"Fecha inválida: {txt}")
    dd = parts[0].zfill(2)
    mm = parts[1].zfill(2)
    yyyy = parts[2]
    return datetime.strptime(f"{dd}/{mm}/{yyyy}", '%d/%m/%Y').date()


def file_upload_view(request):
    if request.method == 'POST':
        form = FileUploadForm(request.POST, request.FILES)

        # 🔎 Trazas útiles para ver qué llega
        print('DEBUG upload: METHOD=', request.method)
        print('DEBUG upload: CONTENT_TYPE=', request.META.get('CONTENT_TYPE'))
        print('DEBUG upload: FILES_len=', len(request.FILES), 'keys=', list(request.FILES.keys()))

        files = request.FILES.getlist('files')  # 👈 clave
        if not files:
            form.add_error('files', 'Seleccione al menos un archivo .csv')
            return render(request, 'upload.html', {'form': form})

        # Determinar tipo por el botón
        if 'submit_depositos' in request.POST:
            tipo = 'depositos'
        elif 'submit_cheques' in request.POST:
            tipo = 'cheques'
        elif 'submit_efectivos' in request.POST:
            tipo = 'efectivos'

        for f in files:
            f.seek(0)  # por si el puntero se movió
            handle_uploaded_file(f, tipo)

        messages.success(request, f'{len(files)} archivo(s) procesados como {tipo}.')
        return redirect('/avances/upload')  # o usa {% url 'avances' %}

    # GET
    return render(request, 'upload.html', {'form': FileUploadForm()})


def limpiar_monto(val):
    # None / NaN
    if val is None or (isinstance(val, float) and pd.isna(val)) or (hasattr(pd, 'isna') and pd.isna(val)):
        return None

    # Si ya es numérico
    if isinstance(val, Decimal):
        return val
    if isinstance(val, (int, float)):
        return Decimal(str(val))

    # Si es texto con símbolos (RD$, comas, espacios, paréntesis negativos)
    s = str(val).strip()

    # ¿negativo tipo (1,234.56)?
    neg = s.startswith('(') and s.endswith(')')
    if neg:
        s = s[1:-1]

    # quita símbolos de moneda y espacios
    s = s.replace('RD$', '').replace('$', '').replace(' ', '')

    # normaliza separadores:
    # - si hay coma y punto: asumimos coma = miles → la quitamos
    if ',' in s and '.' in s:
        s = s.replace(',', '')
    # - si solo hay coma: asumimos coma = decimal
    elif ',' in s and '.' not in s:
        s = s.replace(',', '.')

    # deja solo dígitos, punto y signo
    s = re.sub(r'[^0-9\.\-]', '', s)

    # si quedaron múltiples puntos, deja solo el último como decimal
    if s.count('.') > 1:
        last = s.rfind('.')
        s = s[:last].replace('.', '') + s[last:]

    if s in ('', '.', '-', '-.'):
        return None

    d = Decimal(s)
    return -d if neg else d

def read_csv_upload(fileobj, dtype=None):
    """
    Lee un CSV subido vía Django:
    - Lee bytes una sola vez y prueba encodings comunes.
    - Decodifica a str y usa StringIO -> evita 'bytes-like object' con engine='python'.
    - Autodetecta separador (coma, punto y coma, tab).
    Devuelve: (df, encoding_usado)
    """
    import pandas as pd
    from io import StringIO

    # lee bytes una vez
    raw = fileobj.read()
    try:
        fileobj.seek(0)   # por si luego necesitas reutilizar 'f'
    except Exception:
        pass

    last_err = None
    for enc in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
        try:
            text = raw.decode(enc, errors='strict')      # a str
            sio = StringIO(text)
            df = pd.read_csv(
                sio,
                dtype=dtype,
                sep=None,            # autodetecta , ; \t
                engine='python'      # requerido para sep=None
            )
            # limpieza mínima de encabezados (sin “normalizar” nombres):
            # quita BOM/espacios raros que rompen claves como 'Fecha'
            df.rename(columns=lambda c: str(c).replace('\ufeff', '').replace('\xa0', ' ').strip(), inplace=True)
            return df, enc
        except Exception as e:
            last_err = e
            continue

    raise ValueError(f"No se pudo leer el CSV con los encodings probados. Último error: {last_err}")


def handle_uploaded_file(f,tipo):
    # Lógica para manejar y procesar el archivo subido
    if tipo == 'depositos':
        # 1) Leer CSV robustamente y preservar columnas como texto
        df, enc = read_csv_upload(
            f,
            dtype={'No. de cuenta': 'string', 'Monto': 'string', 'Fecha': 'string'}
        )
        print(f"CSV '{f.name}' leído con encoding {enc}")

        # 2) Fecha: global (en filename mm-dd-yy) o por fila (columna Fecha dd/mm/YYYY)
        fecha_global = parse_fecha_from_filename(f.name)   # -> date | None
        usar_fecha_por_fila = (fecha_global is None)

        # 3) Prefetch: map de cuenta (normalizada) -> pk
        cuentas_map = dict(
            Cosechero.objects
            .filter(numero_cuenta_banco__isnull=False)
            .values_list('numero_cuenta_banco', 'pk')
        )

        # 4) Cachés locales para eficiencia y CONSISTENCIA
        cosecheros_cache: dict[int, Cosechero] = {}
        ventas_cache: dict[tuple[int, date], Venta] = {}
        depositos_creados = []
        errores = []

        for index, row in df.iterrows():
            cuenta = limpiar_cuenta(row.get('No. de cuenta'))
            monto  = limpiar_monto(row.get('Monto'))

            if not cuenta or monto is None:
                continue

            cosechero_pk = cuentas_map.get(cuenta)
            if not cosechero_pk:
                print(f"No se encontró Cosechero con cuenta '{cuenta}' (fila {index}).")
                continue

            # 5) Cosechero SIEMPRE por iteración (nunca uses locals())
            c_obj = cosecheros_cache.get(cosechero_pk)
            if c_obj is None:
                c_obj = Cosechero.objects.get(pk=cosechero_pk)
                cosecheros_cache[cosechero_pk] = c_obj

            # 6) Fecha de avance y sábado de agrupación
            if usar_fecha_por_fila:
                try:
                    fecha_avance = parse_fecha_cell_ddmmyyyy(row.get('Fecha'))
                except Exception as e:
                    print(f"Fila {index}: fecha inválida '{row.get('Fecha')}'. {e}")
                    continue
            else:
                fecha_avance = fecha_global

            fecha_sabado = proximo_sabado(fecha_avance)
            key = (cosechero_pk, fecha_sabado)

            try:
                with transaction.atomic():
                    # 7) Resolver/crear la venta del sábado para este cosechero
                    venta = ventas_cache.get(key)
                    if venta is None:
                        venta = obtener_venta_existente(cosechero_pk, fecha_sabado)
                        if venta is None:
                            venta = Venta.objects.create(
                                cosechero=c_obj,
                                fecha_venta=fecha_sabado,
                                impreso=False,
                                total=monto,
                                cosecha_id=10002
                            )
                        else:
                            # Seguridad: la venta debe pertenecer al mismo cosechero
                            if venta.cosechero_id != c_obj.id:
                                raise ValueError(
                                    f"Venta {venta.id} pertenece a cosechero {venta.cosechero_id}, "
                                    f"no a {c_obj.id} (fila {index})"
                                )
                            venta.total = (Decimal(venta.total) if not isinstance(venta.total, Decimal) else venta.total) + monto
                            venta.save()
                        ventas_cache[key] = venta
                    else:
                        venta.total = (Decimal(venta.total) if not isinstance(venta.total, Decimal) else venta.total) + monto
                        venta.save()

                    # 8) Invariante dura (evita cruzar cosecheros)
                    assert venta.cosechero_id == c_obj.id, \
                        f"Invariante rota: venta {venta.id} cosechero={venta.cosechero_id} vs avance cosechero={c_obj.id}"

                    # 9) Crear avance y su detalle
                    avance = Avance.objects.create(
                        cosechero=c_obj,
                        monto_pagado=monto,
                        fecha=fecha_avance,
                        numero=1,
                        descripcion="Avance a cosecha",
                        tipo_avance='deposito',
                        estado='realizado'
                    )
                    DetalleAvance.objects.create(
                        venta=venta,
                        avance=avance,
                        monto=monto
                    )
                    depositos_creados.append({
                        'fila': index,
                        'cosechero_id': c_obj.id,
                        'cosechero': str(c_obj),
                        'fecha': fecha_avance,
                        'monto': monto,
                        'venta_id': venta.id,
                        'fecha_sabado': fecha_sabado
                    })


            except Exception as e:
                errores.append({
                    'fila': index,
                    'cuenta': cuenta,
                    'error': str(e),
                })
                print(f"Error fila {index} (cuenta {cuenta}): {e}")
                continue
        

        print("\n===== RESUMEN DE DEPÓSITOS CREADOS =====")
        for d in depositos_creados:
            print(
                f"Fila {d['fila']} | "
                f"Cosechero={d['cosechero']} | "
                f"Fecha={d['fecha']} | "
                f"Monto={d['monto']} | "
                f"VentaID={d['venta_id']} | "
                f"Sábado={d['fecha_sabado']} | "
                
                
            )

        print(f"\nTOTAL DEPÓSITOS CREADOS: {len(depositos_creados)}")
        total_monto = sum(d['monto'] for d in depositos_creados)
        print(f"\nMONTO TOTAL DEPÓSITOS CREADOS: {total_monto}")

        if errores:
            print("\n===== ERRORES =====")
            for er in errores:
                print(f"Fila {er['fila']} | Cuenta={er['cuenta']} | Error={er['error']}")
            print(f"\nTOTAL ERRORES: {len(errores)}")

        
        # ...
    elif 'cheques' == tipo:
        # 1) Leer CSV reusando nuestra función robusta de encodings
        #    - Preservamos 'No. Cheque' como string para no perder ceros a la izquierda
        df, enc = read_csv_upload(
            f,
            dtype={'Fecha': 'string', 'No. Cheque': 'string', 'Monto': 'string', 'ID': 'string', 'Cosechero': 'string'}
        )
        required = {'Fecha', 'No. Cheque', 'Monto', 'ID'}
        faltan = required - set(df.columns)
        if faltan:
            raise ValueError(f"Faltan columnas: {sorted(faltan)} | Columns leídas: {list(df.columns)}")
        print(f"CSV '{f.name}' leído con encoding {enc}")

        # 2) Caches locales para eficiencia
        cosecheros_cache: dict[int, Cosechero] = {}
        ventas_cache: dict[tuple[int, date], Venta] = {}

        # (Opcional) métricas simples
        creados_ventas = actualizados_ventas = creados_avances = omitidos = 0

        for index, row in df.iterrows():
            try:
                # 3) Tomamos columnas tal cual (tú te encargas de los nombres en el CSV)
                raw_id = row['ID']
                raw_monto = row['Monto']
                raw_fecha = row['Fecha']
                nro_chq = (row['No. Cheque'] or "").strip() if pd.notna(row['No. Cheque']) else ""
                texto_cosechero = (row['Cosechero'] or "").strip() if 'Cosechero' in df.columns and pd.notna(row['Cosechero']) else ""

                # Validaciones mínimas
                if pd.isna(raw_id) or pd.isna(raw_monto) or pd.isna(raw_fecha) or not nro_chq:
                    omitidos += 1
                    continue

                cosechero_id = int(str(raw_id).strip())
                monto = limpiar_monto(raw_monto)
                if monto is None:
                    omitidos += 1
                    continue

                # Fecha de avance y sábado de agrupación
                fecha_avance = parse_fecha_cell_ddmmyyyy(str(raw_fecha))
                if not fecha_avance:
                    print(f"Fila {index}: fecha inválida '{raw_fecha}'")
                    omitidos += 1
                    continue
                fecha_sabado = proximo_sabado(fecha_avance)
                key = (cosechero_id, fecha_sabado)

                # 4) Objetos de dominio con transacción atómica por fila
                with transaction.atomic():
                    # Cosechero (cacheado)
                    c_obj = cosecheros_cache.get(cosechero_id)
                    if c_obj is None:
                        c_obj = Cosechero.objects.get(pk=cosechero_id)
                        cosecheros_cache[cosechero_id] = c_obj

                    # Venta del sábado (cacheada y consistente)
                    venta = ventas_cache.get(key)
                    if venta is None:
                        venta = obtener_venta_existente(cosechero_id, fecha_sabado)
                        if venta is None:
                            venta = Venta.objects.create(
                                cosechero=c_obj,
                                fecha_venta=fecha_sabado,
                                impreso=False,
                                total=monto,
                                # si manejas cosecha, descomenta:
                                cosecha_id=10002,
                            )
                            creados_ventas += 1
                        else:
                            # seguridad: misma persona
                            if venta.cosechero_id != c_obj.id:
                                raise ValueError(
                                    f"Venta {venta.id} pertenece a cosechero {venta.cosechero_id}, no a {c_obj.id}"
                                )
                            venta.total = (Decimal(venta.total) if not isinstance(venta.total, Decimal) else venta.total) + monto
                            venta.save()
                            actualizados_ventas += 1
                        ventas_cache[key] = venta
                    else:
                        venta.total = (Decimal(venta.total) if not isinstance(venta.total, Decimal) else venta.total) + monto
                        venta.save()
                        actualizados_ventas += 1

                    # 5) Descripción (regla especial para ID_NO_COSECHERO)
                    if cosechero_id == ID_NO_COSECHERO:
                        descripcion = texto_cosechero or "Descargo de cheque"
                    else:
                        descripcion = "Avance a cosecha"

                    # 6) (Opcional) evitar duplicados exactos del mismo cheque
                    # existe = Avance.objects.filter(
                    #     cosechero=c_obj, fecha=fecha_avance, numero=nro_chq,
                    #     monto_pagado=monto, tipo_avance='cheque'
                    # ).exists()
                    # if existe:
                    #     omitidos += 1
                    #     continue

                    # 7) Crear avance + detalle
                    avance = Avance.objects.create(
                        cosechero=c_obj,
                        monto_pagado=monto,
                        fecha=fecha_avance,
                        numero=nro_chq,
                        descripcion=descripcion,
                        tipo_avance='cheque',
                        estado='realizado'
                    )
                    DetalleAvance.objects.create(
                        venta=venta,
                        avance=avance,
                        monto=monto
                    )
                    creados_avances += 1

                print(f"[OK] {fecha_avance} #{nro_chq} → Cosechero {cosechero_id} (+{monto})")

            except Cosechero.DoesNotExist:
                print(f"Cosechero con ID {row.get('ID')} no encontrado. (Fila {index})")
                omitidos += 1
            except Exception as e:
                print(f"Error fila {index} (cheque {row.get('No. Cheque')}): {e}")
                omitidos += 1

        print(f"Ventas nuevas: {creados_ventas} | Ventas actualizadas: {actualizados_ventas} | Avances creados: {creados_avances} | Omitidos: {omitidos}")

    elif tipo == 'efectivos':
        # 1) Leer Excel (xlsx) preservando columnas como texto
        #    - Usa openpyxl para .xlsx (pip install openpyxl)
        df = pd.read_excel(
        f,
        engine="openpyxl",
        dtype={  # preserva cadenas donde importa
            'Numero': 'string',
            'Monto': 'string',
            'Descripcion': 'string',
            'ID': 'string',
        }
     )

        # 2) Normaliza encabezados mínimos
        df.rename(columns=lambda c: str(c).replace('\ufeff', '').replace('\xa0', ' ').strip(), inplace=True)

        # 3) Valida columnas
        required = {'Fecha', 'Numero', 'Monto', 'ID'}
        faltan = required - set(df.columns)
        if faltan:
            raise ValueError(f"Faltan columnas: {sorted(faltan)} | Columnas leídas: {list(df.columns)}")

        # 4) Convierte columna Fecha a datetime si acaso llegara como número/mixto
        #    (Excel → Timestamp). dayfirst=True te cubre 11/11/2024 si alguien lo escribe como texto.
        df['Fecha'] = pd.to_datetime(df['Fecha'], dayfirst=True, errors='coerce')

        # 5) Caches (consistencia y rendimiento)
        cosecheros_cache: dict[int, Cosechero] = {}
        ventas_cache: dict[tuple[int, date], Venta] = {}

        creados_ventas = actualizados_ventas = creados_avances = omitidos = 0

        for index, row in df.iterrows():
            try:
                # Fecha (esperamos Timestamp por venir de Excel)
                fecha_ts = row['Fecha']
                if pd.isna(fecha_ts):
                    print(f"Fila {index}: fecha inválida '{row['Fecha']}'")
                    omitidos += 1
                    continue
                # asegura tipo date
                fecha_avance = fecha_ts.date() if hasattr(fecha_ts, "date") else fecha_ts

                # Numero / Descripcion
                numero = (row['Numero'] or "").strip() if pd.notna(row['Numero']) else ""
                descripcion = (row['Descripcion'] or "").strip() if 'Descripcion' in df.columns and pd.notna(row['Descripcion']) else "Avance en efectivo"

                # ID cosechero
                raw_id = row['ID']
                if pd.isna(raw_id):
                    omitidos += 1
                    continue
                try:
                    cosechero_id = int(str(raw_id).strip())
                except Exception:
                    print(f"Fila {index}: ID inválido '{raw_id}'")
                    omitidos += 1
                    continue

                # Monto
                raw_monto = row['Monto']
                monto = limpiar_monto(raw_monto)
                if monto is None or monto <= 0:
                    print(f"Fila {index}: monto inválido '{raw_monto}'")
                    omitidos += 1
                    continue

                # Agrupación por sábado (igual que cheques/depositos)
                fecha_sabado = proximo_sabado(fecha_avance)
                key = (cosechero_id, fecha_sabado)

                with transaction.atomic():
                    # Cosechero cacheado
                    c_obj = cosecheros_cache.get(cosechero_id)
                    if c_obj is None:
                        c_obj = Cosechero.objects.get(pk=cosechero_id)
                        cosecheros_cache[cosechero_id] = c_obj

                    # Venta del sábado cacheada
                    venta = ventas_cache.get(key)
                    if venta is None:
                        venta = obtener_venta_existente(cosechero_id, fecha_sabado)
                        if venta is None:
                            venta = Venta.objects.create(
                                cosechero=c_obj,
                                fecha_venta=fecha_sabado,
                                impreso=False,
                                total=monto,
                                # ajusta si manejas múltiples cosechas:
                                cosecha_id=10002,
                            )
                            creados_ventas += 1
                        else:
                            if venta.cosechero_id != c_obj.id:
                                raise ValueError(f"Venta {venta.id} pertenece a {venta.cosechero_id}, no a {c_obj.id}")
                            venta.total = (Decimal(venta.total) if not isinstance(venta.total, Decimal) else venta.total) + monto
                            venta.save()
                            actualizados_ventas += 1
                        ventas_cache[key] = venta
                    else:
                        venta.total = (Decimal(venta.total) if not isinstance(venta.total, Decimal) else venta.total) + monto
                        venta.save()
                        actualizados_ventas += 1

                    # (Opcional) Anti-duplicado exacto:
                    # existe = Avance.objects.filter(
                    #     cosechero=c_obj, fecha=fecha_avance, numero=numero,
                    #     monto_pagado=monto, tipo_avance='efectivo'
                    # ).exists()
                    # if existe:
                    #     omitidos += 1
                    #     continue

                    # Crear Avance + Detalle
                    avance = Avance.objects.create(
                        cosechero=c_obj,
                        monto_pagado=monto,
                        fecha=fecha_avance,
                        numero=(numero or 1),   # sigues tu patrón
                        descripcion=descripcion,
                        tipo_avance='efectivo',
                        estado='realizado'
                    )
                    DetalleAvance.objects.create(
                        venta=venta,
                        avance=avance,
                        monto=monto
                    )
                    creados_avances += 1

                print(f"[OK EFECTIVO] {fecha_avance} #{numero or '—'} → Cosechero {cosechero_id} (+{monto})")

            except Cosechero.DoesNotExist:
                print(f"Cosechero con ID {row.get('ID')} no encontrado. (Fila {index})")
                omitidos += 1
            except Exception as e:
                print(f"Error fila {index} (efectivo #{row.get('Numero')}): {e}")
                omitidos += 1

        print(f"[EFECTIVOS] Ventas nuevas: {creados_ventas} | Ventas actualizadas: {actualizados_ventas} | Avances creados: {creados_avances} | Omitidos: {omitidos}")