from django.apps import AppConfig


def clear_stale_sessions():
    from django.contrib.sessions.models import Session
    from django.utils import timezone

    Session.objects.filter(expire_date__lt=timezone.now()).delete()


class RiegoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "riego"
