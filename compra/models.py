from django.db import models
from articulo.models import Articulo
from proveedor.models import Proveedor

class Compra(models.Model):
    proveedor = models.ForeignKey(Proveedor, on_delete=models.CASCADE)
    fecha_compra = models.DateField()
    fecha_vencimiento = models.DateField()
    factura = models.CharField(max_length=25)
    NFC = models.CharField(max_length=25)
    articulos = models.ManyToManyField(Articulo, through='DetalleCompra')
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('proveedor', 'factura')

    def __str__(self):
        return f"{self.proveedor} - Factura {self.factura}"

    def delete(self, *args, **kwargs):
        self.is_active = False
        self.save()

from django.db import models

class DetalleCompra(models.Model):
    compra = models.ForeignKey(Compra, on_delete=models.CASCADE)
    articulo = models.ForeignKey(Articulo, on_delete=models.CASCADE)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2,default=0)
    cantidad_restante = models.DecimalField(max_digits=10, decimal_places=2,default=0)
    precio_compra = models.DecimalField(max_digits=10, decimal_places=2)
    precio_venta_sugerido = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if self.cantidad_restante == 0:
            self.is_active = False
        else:
            self.is_active = True
        super(DetalleCompra, self).save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self.is_active = False
        self.save()