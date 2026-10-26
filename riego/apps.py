from django.apps import AppConfig


def clear_stale_sessions():
    from django.contrib.sessions.models import Session
    from django.utils import timezone

    Session.objects.filter(expire_date__lt=timezone.now()).delete()


class RiegoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "riego"

    def ready(self):
        import riego.models  # noqa: F401

        import sys
        if 'migrate' not in sys.argv and 'makemigrations' not in sys.argv and 'test' not in sys.argv:
            try:
                from riego.mqtt import iniciar_escucha_mqtt
                iniciar_escucha_mqtt()
            except Exception as e:
                print(f'[MQTT] No se pudo iniciar la escucha automática: {e}')
