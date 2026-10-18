import json
import threading
import uuid

import paho.mqtt.client as mqtt
from django.conf import settings


class MQTTError(Exception):
    pass


_mqtt_thread = None


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


def procesar_mensaje_telemetry_json(topic, payload_dict):
    """
    Procesa JSON de HiveMQ con formato:
    {"ManuelSuculenta1":71,"ManuelCactuscholla1":72,"temp":24.2,"hum_amb":71.3,
     "valvula":"abierta","servo_ManuelSuculenta1":"abierto",...}
    """
    from .models import Planta, DatosAmbientales
    from django.utils import timezone

    datos = DatosAmbientales.get_datos()

    if 'temp' in payload_dict:
        try:
            datos.temperatura = float(payload_dict['temp'])
        except (ValueError, TypeError):
            pass
    if 'hum_amb' in payload_dict:
        try:
            datos.humedad_ambiente = float(payload_dict['hum_amb'])
        except (ValueError, TypeError):
            pass
    datos.save()

    for clave, valor in payload_dict.items():
        if clave in ('temp', 'hum_amb', 'valvula', 'planta'):
            continue

        if clave.startswith('servo_'):
            mqtt_id = clave.replace('servo_', '')
            try:
                planta = Planta.objects.get(mqtt_id=mqtt_id)
                planta.estado_servo = str(valor).strip().lower()
                planta.ultima_lectura_mqtt = timezone.now()
                planta.save(update_fields=['estado_servo', 'ultima_lectura_mqtt'])
            except Planta.DoesNotExist:
                pass
            continue

        try:
            planta = Planta.objects.get(mqtt_id=clave)
            planta.humedad_actual = float(valor)
            planta.ultima_lectura_mqtt = timezone.now()
            planta.save(update_fields=['humedad_actual', 'ultima_lectura_mqtt'])
        except (Planta.DoesNotExist, ValueError, TypeError):
            pass


def _mqtt_loop():
    """Ejecuta el loop de MQTT en segundo plano."""
    try:
        client = create_mqtt_client()
    except MQTTError as error:
        print(f'[MQTT] No se pudo iniciar: {error}')
        return

    def on_connect(mqtt_client, userdata, flags, reason_code, properties):
        topic_filter = settings.MQTT_SENSOR_TOPIC.format(plant_id='+')
        mqtt_client.subscribe(topic_filter, qos=1)
        print(f'[MQTT] Suscrito a {topic_filter}')

    def on_message(mqtt_client, userdata, message):
        try:
            payload = json.loads(message.payload.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            print(f'[MQTT] JSON inválido en {message.topic}')
            return
        procesar_mensaje_telemetry_json(message.topic, payload)

    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(settings.MQTT_HOST, settings.MQTT_PORT, keepalive=30)
        client.loop_forever()
    except Exception as error:
        print(f'[MQTT] Error: {error}')


def iniciar_escucha_mqtt():
    """Inicia el hilo MQTT si aún no está corriendo."""
    global _mqtt_thread
    if _mqtt_thread is None or not _mqtt_thread.is_alive():
        _mqtt_thread = threading.Thread(target=_mqtt_loop, daemon=True)
        _mqtt_thread.start()
        print('[MQTT] Hilo de escucha iniciado en segundo plano.')
