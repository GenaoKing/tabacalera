# avance/models.py
from django.db import models
from cosecheros.models import Cosechero

class Avance(models.Model):
    cosechero = models.ForeignKey(Cosechero, on_delete=models.CASCADE)
    monto_pagado = models.DecimalField(max_digits=10, decimal_places=2)
    fecha = models.DateField()
    descripcion = models.TextField(blank=True, null=True)
    TIPO_AVANCE_CHOICES = [
        ('cheque', 'Cheque'),
        ('deposito', 'Deposito'),
        ('efectivo', 'Pago Efectivo'),
    ]
    tipo_avance = models.CharField(max_length=10, choices=TIPO_AVANCE_CHOICES)
    numero = models.CharField(max_length=255, blank=True, null=True)
    ESTADOS_CHOICES = [
        ('realizado', 'Realizado'),
        ('cambiado', 'Cambiado'),
        ('nulo', 'Nulo'),
    ]
    estado = models.CharField(max_length=10, choices=ESTADOS_CHOICES, default='realizado')
    is_active = models.BooleanField(default=True)

    def delete(self, *args, **kwargs):
        self.is_active = False
        self.save()

    # ... otros métodos ...
