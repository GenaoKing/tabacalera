from django.db import models

from proveedor.models import Proveedor



class Categoria(models.Model):
    nombre = models.CharField(max_length=255)

    def __str__(self):
        return self.nombre

class Articulo(models.Model):
    descripcion = models.TextField()
    CATEGORIAS_CHOICES = [
        ('abonos', 'Abonos'),
        ('fungicidas', 'Fungicidas'),
        ('insecticidas', 'Insecticidas'),
        ('coadyudantes', 'Coadyudantes'),
        ('herbicidas', 'Herbicidas'),
        ('herramientas', 'Herramientas'),
    ]
    categoria = models.CharField(max_length=50, choices=CATEGORIAS_CHOICES, default='Abonos')
    presentacion = models.CharField(max_length=255)
    cantidad_minima_orden = models.PositiveIntegerField()
    proveedor = models.ForeignKey(Proveedor, on_delete=models.SET_NULL, null=True)
    is_active = models.BooleanField(default=True)

    def delete(self, *args, **kwargs):
        self.is_active = False
        self.save()
    
    def __str__(self):
        return self.descripcion+" - "+self.presentacion + " - " + self.proveedor.nombre
