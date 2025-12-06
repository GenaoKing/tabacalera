from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import DetalleArticulo, DetalleAvance

@receiver(post_save, sender=DetalleArticulo)
@receiver(post_save, sender=DetalleAvance)
@receiver(post_delete, sender=DetalleArticulo)
@receiver(post_delete, sender=DetalleAvance)
def update_venta_total(sender, instance, **kwargs):
    instance.venta.update_total()

