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
            mqtt_id = clave.replace('servo_', '').strip()
            try:
                planta = Planta.objects.filter(mqtt_id__iexact=mqtt_id).first()
                if planta:
                    planta.estado_servo = str(valor).strip().lower()
                    if planta.estado_servo == 'cerrado':
                        planta.riego_activo = False
                    elif planta.estado_servo == 'abierto':
                        planta.riego_activo = True
                    planta.ultima_lectura_mqtt = timezone.now()
                    planta.save(update_fields=['estado_servo', 'riego_activo', 'ultima_lectura_mqtt'])
            except Exception as e:
                print(f'[MQTT] Error actualizando servo de {mqtt_id}: {e}')
            continue

        try:
            planta = Planta.objects.filter(mqtt_id__iexact=clave).first()
            if planta:
                planta.humedad_actual = float(valor)
                planta.ultima_lectura_mqtt = timezone.now()
                planta.save(update_fields=['humedad_actual', 'ultima_lectura_mqtt'])
        except (ValueError, TypeError, Exception) as e:
            print(f'[MQTT] Error actualizando humedad de {clave}: {e}')


def _mqtt_loop():
    """Ejecuta el loop de MQTT en segundo plano."""
    from .models import Planta

    try:
        client = create_mqtt_client()
    except MQTTError as error:
        print(f'[MQTT] No se pudo iniciar: {error}')
        return

    def on_connect(mqtt_client, userdata, flags, reason_code, properties):
        # 1. Tópico principal donde el ESP32 publica la telemetría (riego/datos)
        topico_datos = getattr(settings, 'MQTT_DATA_TOPIC', 'riego/datos')
        mqtt_client.subscribe(topico_datos, qos=1)

        # 2. Tópico por planta (riego/plantas/+/sensores)
        topic_filter = settings.MQTT_SENSOR_TOPIC.format(plant_id='+')
        mqtt_client.subscribe(topic_filter, qos=1)

        # 3. Tópicos adicionales comunes y de estado
        mqtt_client.subscribe('riego/sensores', qos=1)
        mqtt_client.subscribe('riego/estado', qos=1)
        mqtt_client.subscribe('riego/plantas/+/datos', qos=1)
        mqtt_client.subscribe('riego/logs', qos=1)
        print(f'[MQTT] Suscrito a {topico_datos}, {topic_filter} y riego/sensores')

    def on_message(mqtt_client, userdata, message):
        try:
            payload_raw = message.payload.decode('utf-8').strip()
            payload = json.loads(payload_raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            texto = message.payload.decode('utf-8', errors='replace').strip()
            # Mensajes de texto del ESP32 como "Planta ManuelSuculenta1: riego terminado"
            for p in Planta.objects.all():
                if p.mqtt_id and p.mqtt_id.lower() in texto.lower():
                    if 'terminado' in texto.lower() or 'cerrando' in texto.lower():
                        p.estado_servo = 'cerrado'
                        p.riego_activo = False
                        p.save(update_fields=['estado_servo', 'riego_activo'])
                    elif 'iniciado' in texto.lower():
                        p.estado_servo = 'abierto'
                        p.riego_activo = True
                        p.save(update_fields=['estado_servo', 'riego_activo'])
            return

        if isinstance(payload, dict):
            procesar_mensaje_telemetry_json(message.topic, payload)
            update_plant_from_telemetry(message.topic, payload)

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
