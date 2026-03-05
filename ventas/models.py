#ventas/models.py
from django.db import models
from django.forms import ValidationError
from cosecheros.models import Cosechero, Cosecha
from articulo.models import Articulo
from avance.models import Avance

# Modelo principal de Venta
class Venta(models.Model):
    cosechero = models.ForeignKey(Cosechero, on_delete=models.CASCADE)
    cosecha = models.ForeignKey(Cosecha, on_delete=models.CASCADE, related_name='ventas')
    fecha_venta = models.DateField()
    total = models.DecimalField(max_digits=10, decimal_places=2)  # Total de la venta.
    impreso = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    def update_total(self):
        total_articulos = sum([detalle.precio_venta_final * detalle.cantidad for detalle in self.detalle_articulos.all()])
        total_avances = sum([detalle.monto for detalle in self.detalle_avances.all()])
        
        self.total = total_articulos + total_avances
        self.save()
    
    def clean(self):
        super().clean()
        if self.id and not (self.detalle_articulos.exists() or self.detalle_avances.exists()):
            raise ValidationError("La venta debe tener al menos un artículo o un avance.")

    def delete(self, *args, **kwargs):
        self.is_active = False
        self.save()

    def __str__(self):
        return f"Venta {self.id} a {self.cosechero}"

# Detalle de los artículos vendidos en una venta
class DetalleArticulo(models.Model):
    venta = models.ForeignKey(Venta, related_name='detalle_articulos', on_delete=models.CASCADE)
    articulo = models.ForeignKey(Articulo, on_delete=models.CASCADE)
    cantidad = models.PositiveIntegerField()
    precio_venta_final = models.DecimalField(max_digits=10, decimal_places=2)  # El precio al que realmente se vendió el artículo.

    def __str__(self):
        return f"{self.cantidad} de {self.articulo}"

# Detalle de los avances en una venta
class DetalleAvance(models.Model):
    venta = models.ForeignKey(Venta, related_name='detalle_avances', on_delete=models.CASCADE)
    avance = models.ForeignKey(Avance, on_delete=models.CASCADE)
    monto = models.DecimalField(max_digits=10, decimal_places=2)  # Monto del avance.

    def __str__(self):
        return f"Avance de {self.monto} a {self.venta.cosechero}"
