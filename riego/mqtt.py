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
    from .models import Planta, DatosAmbientales
    from django.utils import timezone

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

    plants = Planta.objects.filter(mqtt_id=mqtt_id).select_related('usuario')
    if not plants.exists():
        try:
            plants = Planta.objects.filter(pk=int(mqtt_id)).select_related('usuario')
        except ValueError:
            return False

    planta = plants.first()
    if not planta:
        return False

    now = timezone.now()
    planta.temperatura_actual = temperature
    planta.humedad_actual = humidity
    planta.ultima_lectura_mqtt = now
    planta.save(update_fields=['temperatura_actual', 'humedad_actual', 'ultima_lectura_mqtt'])

    # Solo actualizar los datos ambientales del cliente dueño de esta planta
    datos = DatosAmbientales.get_datos(usuario=planta.usuario)
    datos.temperatura = temperature
    datos.humedad_ambiente = humidity
    datos.fecha_actualizacion = now
    datos.save()
    return True


def procesar_mensaje_telemetry_json(topic, payload_dict):
    """
    Procesa JSON de HiveMQ con formato:
    {"ManuelSuculenta1":71,"ManuelCactuscholla1":72,"temp":24.2,"hum_amb":71.3,
     "valvula":"abierta","servo_ManuelSuculenta1":"abierto",...}

    Cada cliente publica o tiene lecturas asociadas a sus propias plantas.
    Los datos ambientales (temperatura y humedad ambiente) se asignan
    estrictamente al cliente al que corresponden las plantas del mensaje.
    """
    from .models import Planta, DatosAmbientales
    from django.contrib.auth.models import User
    from django.utils import timezone

    ahora = timezone.now()
    usuario_detectado = None

    # 1. Detectar usuario desde campos del payload si vienen explícitos
    for k in ('usuario', 'cliente', 'user', 'username'):
        val = payload_dict.get(k)
        if val:
            usuario_detectado = User.objects.filter(username__iexact=str(val).strip()).first()
            if usuario_detectado:
                break

    # 2. Si no viene en el payload, intentar detectar por el tópico (ej: riego/manuel/datos)
    if not usuario_detectado and topic:
        partes = [p.strip() for p in topic.split('/') if p.strip()]
        for parte in partes:
            u = User.objects.filter(username__iexact=parte).first()
            if u:
                usuario_detectado = u
                break

    usuarios_afectados = set()
    if usuario_detectado:
        usuarios_afectados.add(usuario_detectado)

    # 3. Procesar lecturas de cada planta y asociar su respectivo usuario
    for clave, valor in payload_dict.items():
        if clave in ('temp', 'hum_amb', 'temperatura', 'humedad_ambiente', 'valvula', 'planta', 'usuario', 'cliente', 'user', 'username'):
            continue

        if clave.startswith('servo_'):
            mqtt_id = clave.replace('servo_', '').strip()
            try:
                planta = Planta.objects.filter(mqtt_id__iexact=mqtt_id).select_related('usuario').first()
                if planta:
                    usuarios_afectados.add(planta.usuario)
                    planta.estado_servo = str(valor).strip().lower()
                    if planta.estado_servo == 'cerrado':
                        planta.riego_activo = False
                    elif planta.estado_servo == 'abierto':
                        planta.riego_activo = True
                    planta.ultima_lectura_mqtt = ahora
                    planta.save(update_fields=['estado_servo', 'riego_activo', 'ultima_lectura_mqtt'])
            except Exception as e:
                print(f'[MQTT] Error actualizando servo de {mqtt_id}: {e}')
            continue

        try:
            planta = Planta.objects.filter(mqtt_id__iexact=clave).select_related('usuario').first()
            if planta:
                usuarios_afectados.add(planta.usuario)
                planta.humedad_actual = float(valor)
                planta.ultima_lectura_mqtt = ahora
                planta.save(update_fields=['humedad_actual', 'ultima_lectura_mqtt'])
        except (ValueError, TypeError, Exception) as e:
            print(f'[MQTT] Error actualizando humedad de {clave}: {e}')

    # 4. Actualizar datos ambientales SOLO para el/los cliente(s) a los que corresponden estas lecturas
    temp_val = None
    for k in ('temp', 'temperatura'):
        if k in payload_dict:
            try:
                temp_val = float(payload_dict[k])
                break
            except (ValueError, TypeError):
                pass

    hum_amb_val = None
    for k in ('hum_amb', 'humedad_ambiente'):
        if k in payload_dict:
            try:
                hum_amb_val = float(payload_dict[k])
                break
            except (ValueError, TypeError):
                pass

    if temp_val is not None or hum_amb_val is not None:
        for usr in usuarios_afectados:
            datos = DatosAmbientales.get_datos(usuario=usr)
            if temp_val is not None:
                datos.temperatura = temp_val
            if hum_amb_val is not None:
                datos.humedad_ambiente = hum_amb_val
            datos.fecha_actualizacion = ahora
            datos.save()


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

        # 3. Tópicos adicionales comunes y por cliente
        mqtt_client.subscribe('riego/sensores', qos=1)
        mqtt_client.subscribe('riego/estado', qos=1)
        mqtt_client.subscribe('riego/plantas/+/datos', qos=1)
        mqtt_client.subscribe('riego/+/datos', qos=1)
        mqtt_client.subscribe('riego/+/sensores', qos=1)
        mqtt_client.subscribe('riego/logs', qos=1)
        print(f'[MQTT] Suscrito a {topico_datos}, {topic_filter}, tópicos por cliente y riego/sensores')

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
