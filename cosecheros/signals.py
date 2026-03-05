# cosecheros/signals.py
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from .models import Cosechero
from avance.models import Avance

@receiver(pre_delete, sender=Cosechero)
def deactivate_related_avances(sender, instance, **kwargs):
    # Establecer todos los avances asociados como inactivos
    Avance.Cheque.objects.filter(cosechero=instance).update(is_active=False)
    Avance.Deposito.objects.filter(cosechero=instance).update(is_active=False)
    Avance.PagoEfectivo.objects.filter(cosechero=instance).update(is_active=False)
