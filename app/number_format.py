"""Formato numérico visible compartido por HTML, reportes y exportaciones."""

from decimal import Decimal, InvalidOperation


def format_number(value) -> str:
    """Devuelve un valor numérico con miles y exactamente dos decimales."""
    if value in (None, ''):
        return '0.00'
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return '0.00'
    return f'{number:,.2f}'


def format_money(value, symbol='$') -> str:
    """Añade el símbolo indicado al formato numérico institucional."""
    return f'{symbol}{format_number(value)}'
