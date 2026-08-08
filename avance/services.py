# avance/services.py
"""
Servicio unificado de importación de avances.
Flujo: parse_file() → preview JSON → import_rows()
"""
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import StringIO
from pathlib import Path
from typing import Optional

import pandas as pd
from django.db import transaction

from app.business_dates import proximo_sabado
from avance.models import Avance
from cosecheros.models import Cosechero, Cosecha
from ventas.models import Venta, DetalleAvance


# ─────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────
ID_NO_COSECHERO = 30002  # Descargo (cheques que NO son de cosecheros)

# Firmas de columnas para auto-detección de formato
FORMAT_SIGNATURES = {
    'banco_depositos': {'No. de cuenta', 'Monto', 'Beneficiario'},
    'cheques':         {'No. Cheque', 'Monto', 'ID'},
    'efectivos':       {'Numero', 'Monto', 'ID'},
    'unificado':       {'Tipo', 'Monto'},
}


# ─────────────────────────────────────────────
# Utilidades de limpieza
# ─────────────────────────────────────────────
def limpiar_cuenta(valor) -> Optional[str]:
    """Normaliza número de cuenta: solo dígitos."""
    if pd.isna(valor):
        return None
    s = re.sub(r'\D+', '', str(valor).strip())
    return s or None


def limpiar_monto(val) -> Optional[Decimal]:
    """Parsea monto con soporte para RD$, comas, paréntesis negativos, etc."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, Decimal):
        return val
    if isinstance(val, (int, float)):
        return Decimal(str(val))

    s = str(val).strip()
    neg = s.startswith('(') and s.endswith(')')
    if neg:
        s = s[1:-1]

    s = s.replace('RD$', '').replace('$', '').replace(' ', '')

    if ',' in s and '.' in s:
        s = s.replace(',', '')
    elif ',' in s and '.' not in s:
        s = s.replace(',', '.')

    s = re.sub(r'[^0-9.\-]', '', s)

    if s.count('.') > 1:
        last = s.rfind('.')
        s = s[:last].replace('.', '') + s[last:]

    if s in ('', '.', '-', '-.'):
        return None

    try:
        d = Decimal(s)
        return -d if neg else d
    except InvalidOperation:
        return None


def parse_fecha(val) -> Optional[date]:
    """Intenta parsear una fecha de múltiples formatos."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, date):
        return val
    if isinstance(val, datetime):
        return val.date()
    if hasattr(val, 'date'):  # pandas Timestamp
        return val.date()

    s = str(val).strip()
    if not s:
        return None

    # Intentar varios formatos
    for fmt in ('%d/%m/%Y', '%m/%d/%Y', '%Y-%m-%d', '%d-%m-%Y', '%m-%d-%y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_fecha_from_filename(fname: str) -> Optional[date]:
    """Extrae fecha mm-dd-yy del nombre del archivo."""
    name = Path(fname).stem
    m = re.search(r'\b(\d{2})-(\d{2})-(\d{2})\b', name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(0), '%m-%d-%y').date()
    except ValueError:
        return None


# ─────────────────────────────────────────────
# Lectura de archivos
# ─────────────────────────────────────────────
def read_uploaded_file(fileobj) -> pd.DataFrame:
    """Lee CSV o XLSX, auto-detecta encoding para CSV."""
    fname = getattr(fileobj, 'name', '')
    ext = Path(fname).suffix.lower()

    if ext in ('.xlsx', '.xls'):
        fileobj.seek(0)
        df = pd.read_excel(fileobj, engine='openpyxl', dtype=str)
    else:
        # CSV con auto-detección de encoding
        raw = fileobj.read()
        try:
            fileobj.seek(0)
        except Exception:
            pass

        df = None
        for enc in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
            try:
                text = raw.decode(enc, errors='strict')
                sio = StringIO(text)
                df = pd.read_csv(sio, dtype=str, sep=None, engine='python')
                break
            except Exception:
                continue

        if df is None:
            raise ValueError("No se pudo leer el archivo con los encodings probados.")

    # Limpiar encabezados
    df.rename(
        columns=lambda c: str(c).replace('\ufeff', '').replace('\xa0', ' ').strip(),
        inplace=True
    )

    # Normalizar nombres de columnas comunes (case-insensitive)
    # Así "No. cuenta", "No. Cuenta", "NO. CUENTA" → "No. Cuenta"
    COLUMN_ALIASES = {
        'no. cuenta':       'No. Cuenta',
        'no. de cuenta':    'No. de cuenta',
        'no. cheque':       'No. Cheque',
        'numero':           'Numero',
        'monto':            'Monto',
        'fecha':            'Fecha',
        'tipo':             'Tipo',
        'id':               'ID',
        'beneficiario':     'Beneficiario',
        'descripcion':      'Descripcion',
        'descripción':      'Descripcion',
        'cosechero':        'Cosechero',
    }
    df.rename(
        columns=lambda c: COLUMN_ALIASES.get(c.strip().lower(), c),
        inplace=True
    )

    return df


def detect_format(columns: set) -> str:
    """
    Detecta el formato del archivo. Prioriza señales explícitas (Tipo, No. Cheque,
    Beneficiario) sobre genéricas (Numero) para evitar mis-detección.
    """
    # 1. Señal MÁS explícita: el usuario declaró el tipo por fila
    if {'Tipo', 'Monto'}.issubset(columns):
        return 'unificado'
    # 2. No. Cheque presente → cheques
    if {'No. Cheque', 'Monto', 'ID'}.issubset(columns):
        return 'cheques'
    # 3. Beneficiario + cuenta → export bancario
    if {'No. de cuenta', 'Monto', 'Beneficiario'}.issubset(columns):
        return 'banco_depositos'
    # 4. Fallback más genérico
    if {'Numero', 'Monto', 'ID'}.issubset(columns):
        return 'efectivos'
    return 'desconocido'


# ─────────────────────────────────────────────
# PASO 1: Parsear archivo → preview JSON
# ─────────────────────────────────────────────
def parse_file_for_preview(fileobj) -> dict:
    """
    Lee el archivo, detecta formato, valida cada fila.
    Retorna un dict con la estructura del preview para el frontend.
    """
    df = read_uploaded_file(fileobj)
    columns = set(df.columns)
    formato = detect_format(columns)
    filename = getattr(fileobj, 'name', 'archivo')

    # Intentar fecha del filename (para depósitos del banco)
    fecha_filename = parse_fecha_from_filename(filename)

    # Pre-cargar lookups de cosecheros
    cosecheros_by_cuenta = {}
    cosecheros_by_id = {}
    cosecheros_list = []  # Para el dropdown de selección manual

    for c in Cosechero.objects.filter(is_active=True):
        cosecheros_list.append({
            'id': c.id,
            'nombre': f"{c.nombre} {c.apellido}".strip(),
            'cuenta': limpiar_cuenta(c.numero_cuenta_banco) if hasattr(c, 'numero_cuenta_banco') else None,
        })
        cosecheros_by_id[c.id] = c
        cuenta = limpiar_cuenta(c.numero_cuenta_banco) if hasattr(c, 'numero_cuenta_banco') else None
        if cuenta:
            cosecheros_by_cuenta[cuenta] = c

    # Parsear filas según formato
    rows = []

    if formato == 'banco_depositos':
        rows = _parse_banco_depositos(df, cosecheros_by_cuenta, fecha_filename)
    elif formato == 'cheques':
        rows = _parse_cheques(df, cosecheros_by_id)
    elif formato == 'efectivos':
        rows = _parse_efectivos(df, cosecheros_by_id)
    elif formato == 'unificado':
        rows = _parse_unificado(df, cosecheros_by_id, cosecheros_by_cuenta)
    else:
        # Intentar detectar como depósito si tiene columnas similares
        raise ValueError(
            f"Formato no reconocido. Columnas: {sorted(columns)}. "
            f"Se esperaba uno de: {list(FORMAT_SIGNATURES.keys())}"
        )

    # Estadísticas
    validos = sum(1 for r in rows if r['status'] == 'valid')
    warnings = sum(1 for r in rows if r['status'] == 'warning')
    errores = sum(1 for r in rows if r['status'] == 'error')

    return {
        'filename': filename,
        'formato': formato,
        'total_rows': len(rows),
        'validos': validos,
        'warnings': warnings,
        'errores': errores,
        'rows': rows,
        'cosecheros': cosecheros_list,
        'fecha_filename': fecha_filename.isoformat() if fecha_filename else None,
    }


def _build_row(
    index: int,
    cosechero_id: Optional[int],
    cosechero_nombre: str,
    tipo_avance: str,
    numero: str,
    monto: Optional[Decimal],
    fecha: Optional[date],
    descripcion: str,
    cuenta: str = '',
    status: str = 'valid',
    status_msg: str = '',
) -> dict:
    """Construye un dict de fila para el preview."""
    errors = []

    if monto is None or monto <= 0:
        errors.append('Monto inválido')
    if fecha is None:
        errors.append('Fecha vacía o inválida')
    if cosechero_id is None:
        errors.append('Cosechero no encontrado')
    if tipo_avance not in ('cheque', 'deposito', 'efectivo'):
        errors.append(f'Tipo inválido: {tipo_avance}')

    # Determinar estado final
    if errors:
        if cosechero_id is None and len(errors) == 1:
            final_status = 'warning'  # Solo falta cosechero → selección manual
            final_msg = 'Cosechero no encontrado'
        else:
            final_status = 'error'
            final_msg = '; '.join(errors)
    else:
        final_status = status
        final_msg = status_msg

    return {
        'index': index,
        'cosechero_id': cosechero_id,
        'cosechero_nombre': cosechero_nombre,
        'tipo_avance': tipo_avance,
        'numero': numero,
        'monto': str(monto) if monto else None,
        'monto_display': f"{monto:,.2f}" if monto else 'inválido',
        'fecha': fecha.isoformat() if fecha else None,
        'fecha_display': fecha.strftime('%d/%m/%Y') if fecha else 'vacía',
        'descripcion': descripcion,
        'cuenta': cuenta,
        'status': final_status,
        'status_msg': final_msg,
        'selected': final_status in ('valid',),  # Pre-seleccionar solo los válidos
    }


def _parse_banco_depositos(df, cosecheros_by_cuenta, fecha_filename):
    """Parsea formato de export bancario (depósitos)."""
    rows = []
    for idx, row in df.iterrows():
        cuenta = limpiar_cuenta(row.get('No. de cuenta'))
        monto = limpiar_monto(row.get('Monto'))
        beneficiario = str(row.get('Beneficiario', '')).strip() if pd.notna(row.get('Beneficiario')) else ''
        descripcion_raw = str(row.get('Descripcion', '')).strip() if pd.notna(row.get('Descripcion')) else ''

        # Fecha: del filename o de columna si existe
        if 'Fecha' in df.columns and pd.notna(row.get('Fecha')):
            fecha = parse_fecha(row.get('Fecha'))
        else:
            fecha = fecha_filename

        # Lookup por cuenta
        cosechero = cosecheros_by_cuenta.get(cuenta) if cuenta else None
        cosechero_id = cosechero.id if cosechero else None
        cosechero_nombre = f"{cosechero.nombre} {cosechero.apellido}".strip() if cosechero else beneficiario

        rows.append(_build_row(
            index=idx,
            cosechero_id=cosechero_id,
            cosechero_nombre=cosechero_nombre,
            tipo_avance='deposito',
            numero='1',  # Convención para depósitos
            monto=monto,
            fecha=fecha,
            descripcion=descripcion_raw,
            cuenta=cuenta or '',
        ))
    return rows


def _parse_cheques(df, cosecheros_by_id):
    """Parsea formato de cheques."""
    rows = []
    for idx, row in df.iterrows():
        raw_id = row.get('ID')
        monto = limpiar_monto(row.get('Monto'))
        raw_fecha = row.get('Fecha')
        nro_chq = str(row.get('No. Cheque', '')).strip() if pd.notna(row.get('No. Cheque')) else ''
        texto_cosechero = str(row.get('Cosechero', '')).strip() if pd.notna(row.get('Cosechero')) else ''
        descripcion_raw = str(row.get('Descripcion', '')).strip() if pd.notna(row.get('Descripcion')) else ''

        # ID cosechero
        cosechero_id = None
        cosechero_nombre = texto_cosechero
        if pd.notna(raw_id):
            try:
                cid = int(str(raw_id).strip())
                cosechero = cosecheros_by_id.get(cid)
                if cosechero:
                    cosechero_id = cosechero.id
                    cosechero_nombre = f"{cosechero.nombre} {cosechero.apellido}".strip()
            except (ValueError, TypeError):
                pass

        fecha = parse_fecha(raw_fecha)

        rows.append(_build_row(
            index=idx,
            cosechero_id=cosechero_id,
            cosechero_nombre=cosechero_nombre,
            tipo_avance='cheque',
            numero=nro_chq,
            monto=monto,
            fecha=fecha,
            descripcion=descripcion_raw,
        ))
    return rows


def _parse_efectivos(df, cosecheros_by_id):
    """Parsea formato de efectivos."""
    rows = []
    for idx, row in df.iterrows():
        raw_id = row.get('ID')
        monto = limpiar_monto(row.get('Monto'))
        raw_fecha = row.get('Fecha')
        numero = str(row.get('Numero', '')).strip() if pd.notna(row.get('Numero')) else '2'
        descripcion_raw = str(row.get('Descripcion', '')).strip() if pd.notna(row.get('Descripcion')) else ''

        cosechero_id = None
        cosechero_nombre = ''
        if pd.notna(raw_id):
            try:
                cid = int(str(raw_id).strip())
                cosechero = cosecheros_by_id.get(cid)
                if cosechero:
                    cosechero_id = cosechero.id
                    cosechero_nombre = f"{cosechero.nombre} {cosechero.apellido}".strip()
            except (ValueError, TypeError):
                pass

        fecha = parse_fecha(raw_fecha)

        rows.append(_build_row(
            index=idx,
            cosechero_id=cosechero_id,
            cosechero_nombre=cosechero_nombre,
            tipo_avance='efectivo',
            numero=numero,
            monto=monto,
            fecha=fecha,
            descripcion=descripcion_raw,
        ))
    return rows


def _parse_unificado(df, cosecheros_by_id, cosecheros_by_cuenta):
    """
    Parsea formato unificado: archivo con columna 'Tipo' que puede
    mezclar cheques, depósitos y efectivos.
    """
    rows = []
    for idx, row in df.iterrows():
        tipo_raw = str(row.get('Tipo', '')).strip().lower()
        monto = limpiar_monto(row.get('Monto'))
        raw_fecha = row.get('Fecha')
        numero = str(row.get('Numero', '')).strip() if pd.notna(row.get('Numero')) else ''
        descripcion_raw = str(row.get('Descripcion', '')).strip() if pd.notna(row.get('Descripcion')) else ''

        # Normalizar tipo
        tipo_map = {
            'cheque': 'cheque', 'cheques': 'cheque', 'ch': 'cheque',
            'deposito': 'deposito', 'depósito': 'deposito', 'dep': 'deposito', 'depositos': 'deposito',
            'efectivo': 'efectivo', 'ef': 'efectivo', 'efectivos': 'efectivo', 'cash': 'efectivo',
        }
        tipo_avance = tipo_map.get(tipo_raw, tipo_raw)

        # Lookup cosechero: primero por ID, luego por cuenta
        cosechero_id = None
        cosechero_nombre = ''

        raw_id = row.get('ID')
        if pd.notna(raw_id):
            try:
                cid = int(str(raw_id).strip())
                cosechero = cosecheros_by_id.get(cid)
                if cosechero:
                    cosechero_id = cosechero.id
                    cosechero_nombre = f"{cosechero.nombre} {cosechero.apellido}".strip()
            except (ValueError, TypeError):
                pass

        if cosechero_id is None and 'No. Cuenta' in df.columns:
            cuenta = limpiar_cuenta(row.get('No. Cuenta'))
            if cuenta:
                cosechero = cosecheros_by_cuenta.get(cuenta)
                if cosechero:
                    cosechero_id = cosechero.id
                    cosechero_nombre = f"{cosechero.nombre} {cosechero.apellido}".strip()

        fecha = parse_fecha(raw_fecha)

        rows.append(_build_row(
            index=idx,
            cosechero_id=cosechero_id,
            cosechero_nombre=cosechero_nombre,
            tipo_avance=tipo_avance,
            numero=numero,
            monto=monto,
            fecha=fecha,
            descripcion=descripcion_raw,
        ))
    return rows


# ─────────────────────────────────────────────
# PASO 2: Importar filas confirmadas
# ─────────────────────────────────────────────
def obtener_venta_existente(cosechero_id: int, fecha_sabado: date) -> Optional[Venta]:
    """
    Busca una venta existente para el cosechero en la semana del sábado.
    Idéntica a la lógica en ventas/views.py — busca por rango de semana.
    """
    inicio_semana = fecha_sabado - timedelta(days=fecha_sabado.weekday())
    fin_semana = inicio_semana + timedelta(days=6)
    ventas = Venta.objects.filter(
        cosechero_id=cosechero_id,
        fecha_venta__range=(inicio_semana, fin_semana),
    )
    return ventas.first() if ventas.exists() else None


def get_cosechas_list() -> list[dict]:
    """Retorna las cosechas disponibles para el selector del frontend.
    Usa str(cosecha) para el nombre, así funciona sin importar los campos del modelo."""
    return [
        {'id': c.id, 'nombre': str(c)}
        for c in Cosecha.objects.all().order_by('-id')
    ]


def import_confirmed_rows(rows: list[dict], cosecha_id: int, descripcion_default: str) -> dict:
    """
    Importa las filas confirmadas por el usuario.

    Args:
        rows: Filas confirmadas del preview
        cosecha_id: ID de la cosecha seleccionada por el usuario
        descripcion_default: Descripción para filas sin descripción (ej: "Avance a cosecha 2025-2026")
    
    Retorna estadísticas de la importación.
    """
    stats = {
        'avances_creados': 0,
        'ventas_creadas': 0,
        'ventas_actualizadas': 0,
        'errores': [],
    }

    cosecheros_cache: dict[int, Cosechero] = {}
    ventas_cache: dict[tuple[int, date], Venta] = {}

    for row in rows:
        try:
            cosechero_id_row = int(row['cosechero_id'])
            monto = Decimal(str(row['monto']))
            fecha_avance = date.fromisoformat(row['fecha'])
            tipo_avance = row['tipo_avance']
            numero = row.get('numero', '')
            descripcion = row.get('descripcion', '').strip() or descripcion_default

            if tipo_avance not in ('cheque', 'deposito', 'efectivo'):
                stats['errores'].append(
                    f"Fila {row.get('index', '?')}: tipo_avance inválido '{tipo_avance}'"
                )
                continue

            if monto <= 0:
                stats['errores'].append(f"Fila {row.get('index', '?')}: monto inválido ({monto})")
                continue

            fecha_sabado = proximo_sabado(fecha_avance)
            key = (cosechero_id_row, fecha_sabado)

            with transaction.atomic():
                # Cosechero
                c_obj = cosecheros_cache.get(cosechero_id_row)
                if c_obj is None:
                    c_obj = Cosechero.objects.get(pk=cosechero_id_row)
                    cosecheros_cache[cosechero_id_row] = c_obj

                # Venta del sábado (reutiliza si existe en la misma semana)
                venta = ventas_cache.get(key)
                if venta is None:
                    venta = obtener_venta_existente(cosechero_id_row, fecha_sabado)
                    if venta is None:
                        venta = Venta.objects.create(
                            cosechero=c_obj,
                            fecha_venta=fecha_sabado,
                            impreso=False,
                            total=monto,
                            cosecha_id=cosecha_id,
                        )
                        stats['ventas_creadas'] += 1
                    else:
                        venta.total = (
                            Decimal(str(venta.total))
                            if not isinstance(venta.total, Decimal)
                            else venta.total
                        ) + monto
                        venta.save()
                        stats['ventas_actualizadas'] += 1
                    ventas_cache[key] = venta
                else:
                    venta.total = (
                        Decimal(str(venta.total))
                        if not isinstance(venta.total, Decimal)
                        else venta.total
                    ) + monto
                    venta.save()
                    stats['ventas_actualizadas'] += 1

                # Descripción especial para no-cosechero
                if cosechero_id_row == ID_NO_COSECHERO and not descripcion:
                    descripcion = "Descargo de cheque"

                # Crear avance
                avance = Avance.objects.create(
                    cosechero=c_obj,
                    monto_pagado=monto,
                    fecha=fecha_avance,
                    numero=numero or '1',
                    descripcion=descripcion,
                    tipo_avance=tipo_avance,
                    estado='realizado',
                )

                # Crear detalle avance (vinculado a venta)
                DetalleAvance.objects.create(
                    venta=venta,
                    avance=avance,
                    monto=monto,
                )

                stats['avances_creados'] += 1

        except Cosechero.DoesNotExist:
            stats['errores'].append(
                f"Fila {row.get('index', '?')}: Cosechero ID {row.get('cosechero_id')} no existe"
            )
        except Exception as e:
            stats['errores'].append(
                f"Fila {row.get('index', '?')}: {str(e)}"
            )

    return stats
