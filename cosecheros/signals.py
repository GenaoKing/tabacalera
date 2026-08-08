from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from .models import Cosecha, Cosechero
from avance.models import Avance

@receiver(pre_delete, sender=Cosechero)
def deactivate_related_avances(sender, instance, **kwargs):
    # Establecer todos los avances asociados como inactivos
    Avance.objects.filter(cosechero=instance).update(is_active=False)


@receiver(post_save, sender=Cosecha)
def clonar_precios_de_cosecha_anterior(sender, instance, created, **kwargs):
    """Al crear una cosecha nueva, hereda los precios de la más reciente que ya tenga."""
    if not created:
        return

    from .services import clonar_precios, cosecha_mas_reciente_con_precios

    origen = cosecha_mas_reciente_con_precios(excluir=instance)
    if origen is not None:
        clonar_precios(origen, instance)
