from django import template

from app.number_format import format_number


register = template.Library()


@register.filter(name='number_2')
def number_2(value):
    """Formato visible institucional: 10,000.00."""
    return format_number(value)
