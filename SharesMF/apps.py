from django.apps import AppConfig


class SharesmfConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'SharesMF'

    def ready(self):
        import SharesMF.signals