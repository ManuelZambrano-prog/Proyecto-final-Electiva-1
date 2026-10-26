import json

import paho.mqtt.client as mqtt
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from riego.mqtt import MQTTError, create_mqtt_client, update_plant_from_telemetry, procesar_mensaje_telemetry_json


class Command(BaseCommand):
    help = 'Escucha las lecturas de plantas publicadas por MQTT y actualiza sus datos.'

    def handle(self, *args, **options):
        try:
            client = create_mqtt_client()
        except MQTTError as error:
            raise CommandError(str(error)) from error

        def on_connect(mqtt_client, userdata, flags, reason_code, properties):
            topico_datos = getattr(settings, 'MQTT_DATA_TOPIC', 'riego/datos')
            mqtt_client.subscribe(topico_datos, qos=1)
            topic_filter = settings.MQTT_SENSOR_TOPIC.format(plant_id='+')
            mqtt_client.subscribe(topic_filter, qos=1)
            mqtt_client.subscribe('riego/sensores', qos=1)
            self.stdout.write(f'Escuchando {topico_datos} y {topic_filter}')

        def on_message(mqtt_client, userdata, message):
            try:
                payload = json.loads(message.payload.decode('utf-8'))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self.stderr.write(f'Mensaje de texto en {message.topic}: {message.payload.decode("utf-8", errors="replace")}')
                return

            if isinstance(payload, dict):
                procesar_mensaje_telemetry_json(message.topic, payload)
                update_plant_from_telemetry(message.topic, payload)
                self.stdout.write(f'Telemetría procesada de {message.topic}')

        client.on_connect = on_connect
        client.on_message = on_message
        try:
            client.connect(settings.MQTT_HOST, settings.MQTT_PORT, keepalive=30)
            self.stdout.write('Conectado al broker HiveMQ. Ctrl+C para detener.')
            client.loop_forever()
        except KeyboardInterrupt:
            self.stdout.write('Suscriptor MQTT detenido.')
        except Exception as error:
            raise CommandError(f'No se pudo conectar a HiveMQ: {error}') from error