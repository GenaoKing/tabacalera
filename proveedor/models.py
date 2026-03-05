# proveedor/models.py
from django.db import models

class Proveedor(models.Model):
    nombre = models.CharField(max_length=255)
    direccion = models.TextField()
    telefono = models.CharField(max_length=20)
    correo_electronico = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)

    def delete(self, *args, **kwargs):
        self.is_active = False
        self.save()
    
    def __str__(self):
        return self.nombre
