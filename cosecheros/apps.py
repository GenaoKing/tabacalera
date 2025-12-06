from django.apps import AppConfig


class CosecherosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cosecheros"

    def ready(self):
        import cosecheros.signals