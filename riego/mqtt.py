import json
import uuid

import paho.mqtt.client as mqtt
from django.conf import settings


class MQTTError(Exception):
    pass


def create_mqtt_client():
    if not all((settings.MQTT_HOST, settings.MQTT_USERNAME, settings.MQTT_PASSWORD)):
        raise MQTTError('Configura MQTT_HOST, MQTT_USERNAME y MQTT_PASSWORD en el entorno.')

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f'riego-{uuid.uuid4().hex}',
        protocol=mqtt.MQTTv311,
    )
    client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)
    client.tls_set()
    return client


def publish_plant_command(plant, enabled):
    client = create_mqtt_client()
    topic = settings.MQTT_COMMAND_TOPIC.format(plant_id=plant.mqtt_id)
    payload = json.dumps({'planta_id': plant.mqtt_id, 'regar': enabled})

    try:
        client.connect(settings.MQTT_HOST, settings.MQTT_PORT, keepalive=15)
        client.loop_start()
        result = client.publish(topic, payload, qos=1)
        result.wait_for_publish(timeout=10)
        if not result.is_published():
            raise MQTTError('El broker no confirmó la publicación.')
    except MQTTError:
        raise
    except Exception as error:
        raise MQTTError(str(error)) from error
    finally:
        if client.is_connected():
            client.disconnect()
        client.loop_stop()


def update_plant_from_telemetry(topic, payload):
    from .models import Planta

    topic_parts = topic.split('/')
    topic_pattern = settings.MQTT_SENSOR_TOPIC.split('/')
    if len(topic_parts) != len(topic_pattern) or topic_pattern.count('{plant_id}') != 1:
        return False
    plant_id_position = topic_pattern.index('{plant_id}')
    if any(
        expected != '{plant_id}' and expected != actual
        for expected, actual in zip(topic_pattern, topic_parts)
    ):
        return False

    try:
        mqtt_id = topic_parts[plant_id_position]
        temperature = float(payload.get('temperatura', payload.get('temperature')))
        humidity = float(payload.get('humedad', payload.get('humidity')))
    except (TypeError, ValueError, AttributeError):
        return False

    plants = Planta.objects.filter(mqtt_id=mqtt_id)
    if not plants.exists():
        try:
            plants = Planta.objects.filter(pk=int(mqtt_id))
        except ValueError:
            return False

    return plants.update(
        temperatura_actual=temperature,
        humedad_actual=humidity,
    ) == 1