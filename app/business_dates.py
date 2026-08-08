from datetime import date, timedelta


def proximo_sabado(fecha: date) -> date:
    """Retorna el sábado de cierre que corresponde a una fecha operativa."""
    return fecha + timedelta(days=(5 - fecha.weekday()) % 7)
