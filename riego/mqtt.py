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


def _parse_float(val):
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _normalize_servo_state(val):
    if val is None:
        return None
    s = str(val).strip().lower()
    if s in ('abierto', 'abierta', 'open', 'true', '1', 'on', 'activo', 'activa'):
        return 'abierto'
    if s in ('cerrado', 'cerrada', 'close', 'closed', 'false', '0', 'off', 'inactivo', 'inactiva'):
        return 'cerrado'
    return s


def _find_user_from_string(text):
    if not text:
        return None
    from django.contrib.auth.models import User

    clean = str(text).strip()
    # 1. Búsqueda exacta de username
    u = User.objects.filter(username__iexact=clean).first()
    if u:
        return u

    # 2. Si contiene guiones bajos (ej: Manuel_temp, servo_Manuel)
    if '_' in clean:
        partes = clean.split('_')
        for parte in partes:
            if parte:
                u = User.objects.filter(username__iexact=parte).first()
                if u:
                    return u

    # 3. Revisar si algún username es prefijo del texto (ej: ManuelSuculenta1 -> Manuel)
    clean_lower = clean.lower()
    for u in User.objects.all():
        uname = u.username.lower()
        if uname and clean_lower.startswith(uname):
            return u

    return None


def procesar_mensaje_telemetry_json(topic, payload_dict):
    """
    Procesa JSON de HiveMQ con formato completo:
    {
      "ManuelSuculenta1": 0,
      "ManuelCactuscholla1": 0,
      "Manuel_temp": 24.9,
      "Manuel_hum_amb": 72.2,
      "Manuel_valvula": "abierta",
      "servo_ManuelSuculenta1": "abierto",
      "min_ManuelSuculenta1": 30,
      "max_ManuelSuculenta1": 80, ...
    }

    Asigna lecturas, temperatura, humedad ambiental y estado de servo/válvula
    estrictamente según el usuario correspondiente.
    """
    from .models import Planta, DatosAmbientales, Electrovalvula
    from django.contrib.auth.models import User
    from django.utils import timezone

    ahora = timezone.now()
    usuario_detectado = None

    # 1. Detectar usuario explícito desde campos del payload
    for k in ('usuario', 'cliente', 'user', 'username'):
        val = payload_dict.get(k)
        if val:
            usuario_detectado = User.objects.filter(username__iexact=str(val).strip()).first()
            if usuario_detectado:
                break

    # 2. Si no viene en el payload, detectar por tópico (ej: riego/manuel/datos)
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

    temp_por_usuario = {}
    hum_amb_por_usuario = {}
    valvula_por_usuario = {}
    temp_global = None
    hum_amb_global = None
    valvula_global = None

    # 3. Iterar y categorizar cada clave/valor del payload
    for clave, valor in payload_dict.items():
        if not clave:
            continue
        clave_str = str(clave).strip()
        clave_lower = clave_str.lower()

        # A. Servos de planta (ej: servo_ManuelSuculenta1 o ManuelSuculenta1_servo)
        if clave_lower.startswith('servo_') or clave_lower.endswith('_servo'):
            if clave_lower.startswith('servo_'):
                candidato = clave_str[6:].strip()
            else:
                candidato = clave_str[:-6].strip()

            estado_norm = _normalize_servo_state(valor)

            # Verificar si corresponde a una planta registrada
            planta = Planta.objects.filter(mqtt_id__iexact=candidato).select_related('usuario').first()
            if planta:
                usuarios_afectados.add(planta.usuario)
                planta.estado_servo = estado_norm or 'cerrado'
                planta.riego_activo = (planta.estado_servo == 'abierto')
                planta.ultima_lectura_mqtt = ahora
                planta.save(update_fields=['estado_servo', 'riego_activo', 'ultima_lectura_mqtt'])
                Electrovalvula.objects.filter(planta=planta).update(esta_activa=planta.riego_activo)
                continue

            # Si no es planta, verificar si es servo general de un usuario (ej: servo_Manuel)
            usr = _find_user_from_string(candidato)
            if usr:
                usuarios_afectados.add(usr)
                valvula_por_usuario[usr] = 'abierta' if estado_norm == 'abierto' else 'cerrada'
                continue

            # O servo global
            valvula_global = 'abierta' if estado_norm == 'abierto' else 'cerrada'
            continue

        # B. Válvula / Electrovalvula general (ej: Manuel_valvula, valvula_Manuel, valvula)
        if any(clave_lower.endswith(sfx) for sfx in ('_valvula', '_valve')) or any(clave_lower.startswith(pfx) for pfx in ('valvula_', 'valve_')):
            estado_norm = _normalize_servo_state(valor)
            usr = _find_user_from_string(clave_str)
            if usr:
                usuarios_afectados.add(usr)
                valvula_por_usuario[usr] = 'abierta' if estado_norm == 'abierto' else 'cerrada'
            else:
                valvula_global = 'abierta' if estado_norm == 'abierto' else 'cerrada'
            continue

        if clave_lower in ('valvula', 'valve', 'electrovalvula'):
            estado_norm = _normalize_servo_state(valor)
            valvula_global = 'abierta' if estado_norm == 'abierto' else 'cerrada'
            continue

        # C. Temperatura (ej: Manuel_temp, temp, temperatura, Manuel_temperatura)
        if clave_lower in ('temp', 'temperatura', 'temperature'):
            fval = _parse_float(valor)
            if fval is not None:
                temp_global = fval
            continue

        if any(clave_lower.endswith(sfx) for sfx in ('_temp', '_temperatura', '_temperature')) or any(clave_lower.startswith(pfx) for pfx in ('temp_', 'temperatura_')):
            fval = _parse_float(valor)
            if fval is not None:
                # Comprobar si es para una planta específica (ej: temp_ManuelSuculenta1)
                plant_cand = None
                for pfx in ('temp_', 'temperatura_'):
                    if clave_lower.startswith(pfx):
                        plant_cand = clave_str[len(pfx):].strip()
                        break
                p = Planta.objects.filter(mqtt_id__iexact=plant_cand).select_related('usuario').first() if plant_cand else None
                if p:
                    usuarios_afectados.add(p.usuario)
                    p.temperatura_actual = fval
                    p.ultima_lectura_mqtt = ahora
                    p.save(update_fields=['temperatura_actual', 'ultima_lectura_mqtt'])
                else:
                    usr = _find_user_from_string(clave_str)
                    if usr:
                        usuarios_afectados.add(usr)
                        temp_por_usuario[usr] = fval
                    else:
                        temp_global = fval
            continue

        # D. Humedad ambiental (ej: Manuel_hum_amb, hum_amb, humedad_ambiente, Manuel_humedad_ambiente)
        if clave_lower in ('hum_amb', 'humedad_ambiente', 'hum_ambiente', 'humedad_amb', 'humidity_ambient', 'ambient_humidity'):
            fval = _parse_float(valor)
            if fval is not None:
                hum_amb_global = fval
            continue

        if any(clave_lower.endswith(sfx) for sfx in ('_hum_amb', '_humedad_ambiente', '_hum_ambiente', '_humedad_amb')) or any(clave_lower.startswith(pfx) for pfx in ('hum_amb_', 'humedad_ambiente_')):
            fval = _parse_float(valor)
            if fval is not None:
                usr = _find_user_from_string(clave_str)
                if usr:
                    usuarios_afectados.add(usr)
                    hum_amb_por_usuario[usr] = fval
                else:
                    hum_amb_global = fval
            continue

        # E. Umbrales de humedad (ej: min_ManuelSuculenta1, max_ManuelSuculenta1)
        if clave_lower.startswith('min_') or clave_lower.startswith('minimo_') or clave_lower.startswith('umbral_'):
            cand = clave_str.split('_', 1)[1].strip()
            p = Planta.objects.filter(mqtt_id__iexact=cand).first()
            if p:
                fval = _parse_float(valor)
                if fval is not None:
                    p.umbral_humedad = fval
                    p.save(update_fields=['umbral_humedad'])
            continue

        if clave_lower.startswith('max_') or clave_lower.startswith('maximo_'):
            continue

        # F. Metadatos de nombres de plantas o usuarios (ej: Manuel_planta)
        if any(clave_lower.endswith(sfx) for sfx in ('_planta', '_plantas')) or clave_lower in ('planta', 'plantas', 'usuario', 'cliente', 'user', 'username', 'topic'):
            usr = _find_user_from_string(clave_str)
            if usr:
                usuarios_afectados.add(usr)
            continue

        # G. Humedad de cada planta por su mqtt_id directo (ej: ManuelSuculenta1: 71)
        try:
            planta = Planta.objects.filter(mqtt_id__iexact=clave_str).select_related('usuario').first()
            if planta:
                usuarios_afectados.add(planta.usuario)
                fval = _parse_float(valor)
                if fval is not None:
                    planta.humedad_actual = fval
                    planta.ultima_lectura_mqtt = ahora
                    planta.save(update_fields=['humedad_actual', 'ultima_lectura_mqtt'])
                continue
        except Exception as e:
            print(f'[MQTT] Error actualizando humedad de {clave_str}: {e}')

    # 4. Actualizar datos ambientales y temperatura de plantas estrictamente por usuario
    for usr in usuarios_afectados:
        datos = DatosAmbientales.get_datos(usuario=usr)
        hay_cambios = False

        t = temp_por_usuario.get(usr, temp_global)
        if t is not None:
            datos.temperatura = t
            hay_cambios = True
            # Actualizar también temperatura_actual en las plantas del usuario
            Planta.objects.filter(usuario=usr).update(temperatura_actual=t, ultima_lectura_mqtt=ahora)

        h = hum_amb_por_usuario.get(usr, hum_amb_global)
        if h is not None:
            datos.humedad_ambiente = h
            hay_cambios = True

        v = valvula_por_usuario.get(usr, valvula_global)
        if v is not None:
            datos.estado_valvula = v
            hay_cambios = True
            Electrovalvula.objects.filter(planta__usuario=usr).update(esta_activa=(v == 'abierta'))

        if hay_cambios:
            datos.fecha_actualizacion = ahora
            datos.save()

    # Si llegaron datos ambientales globales y no hay usuario específico identificado
    if not usuarios_afectados and (temp_global is not None or hum_amb_global is not None or valvula_global is not None):
        datos_gen = DatosAmbientales.get_datos(usuario=None)
        if temp_global is not None:
            datos_gen.temperatura = temp_global
        if hum_amb_global is not None:
            datos_gen.humedad_ambiente = hum_amb_global
        if valvula_global is not None:
            datos_gen.estado_valvula = valvula_global
        datos_gen.fecha_actualizacion = ahora
        datos_gen.save()


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
