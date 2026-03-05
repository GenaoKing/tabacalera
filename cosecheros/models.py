# cosecheros/models.py
from django.db import models
from django.core.exceptions import ValidationError


def validate_cedula(value):
  cedula = value
  #cleanup
  cedula = cedula.replace('-','') 
  # La cédula debe tener 11 dígitos
  if len(cedula)!= 11:
    raise ValidationError('La cédula debe tener una longitud de 13 caracteres.')
  if (int(cedula[0:3]) != 402 and int(cedula[0:3]) > 121 and int(cedula[0:3]) < 1):
    raise ValidationError('El formato de la cédula debe ser XXX-XXXXXXX-X')
    
  suma = 0
  verificador = 0
  
  for i, n in enumerate(cedula):
    #No ejecutar el ultimo digito
    if( i == len(cedula)-1):
      break
    # Los dígitos pares valen 2 y los impares 1
    multiplicador = 1 if (int(i) % 2) == 0 else 2
    # Se multiplica cada dígito por su paridad
    digito = int(n)*int(multiplicador)
    # Si la multiplicación da de dos dígitos, se suman entre sí
    digito = digito//10 + digito%10 if(digito>9) else digito

    # Y se va haciendo la acumulación de esa suma
    suma = suma + digito

  # Al final se obtiene el verificador con la siguiente fórmula
  verificador = (10 - (suma % 10) ) % 10

  # Se comprueba el verificador
  if not (verificador == int(cedula[-1:])):
     raise ValidationError('La cédula no es válida.')
    


# Create your models here.
class Cosechero(models.Model):
    nombre = models.CharField(blank=False, max_length=255)
    apellido = models.CharField(blank=False, max_length=255)
    cedula = models.CharField(max_length=13, validators=[validate_cedula],blank=True)
    numero_cuenta_banco = models.CharField(max_length=15, blank=True, null=True, unique=True)
    direccion = models.TextField()
    telefono = models.CharField(max_length=20,blank=True)
    terreno_sembrado = models.DecimalField(max_digits=10, decimal_places=2, help_text="Cantidad de terreno sembrado en tareas")
    is_active = models.BooleanField(default=True, null=False)


    def delete(self, *args, **kwargs):
        self.is_active = False
        self.save()

    def __str__(self):
        return self.nombre +' '+ self.apellido

class Cosecha(models.Model):
   nombre = models.CharField(max_length=35, unique=True)
   fecha_inicio = models.DateField()
   fecha_fin = models.DateField()

   def __str__(self):
        return self.nombre

class EntregaTabaco(models.Model):
    VARIEDADES_CHOICES = [
        ('Corojo Original', 'Corojo Original'),
        ('Corojo 99', 'Corojo 99'),
        ('Habano 92', 'Habano 92'),
        ('Criollo 98', 'Criollo 98'),
        ('Piloto Mejorado', 'Piloto Mejorado'),
        ('HVA', 'HVA'),
    ]
    cosechero = models.ForeignKey(Cosechero, on_delete=models.CASCADE)
    cosecha = models.ForeignKey(Cosecha, on_delete=models.CASCADE)
    variedad = models.CharField(max_length=20, choices=VARIEDADES_CHOICES)
    fecha_entrega = models.DateField()
    centro_largo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    centro_corto = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    uno_medio = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    libre_pie = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    picadura = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    rezago = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    criollo = models.DecimalField(max_digits=10, decimal_places=2, default=0)


