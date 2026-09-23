from django.apps import AppConfig


def clear_stale_sessions():
    from django.contrib.sessions.models import Session
    Session.objects.all().delete()


class RiegoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "riego"

    def ready(self):
        clear_stale_sessions()
