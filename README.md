# Proyecto-final-Electiva-1

## Fotos de especies y MQTT

Las fotos del catálogo se guardan en `media/especies/`; configura `MEDIA_ROOT` y un servidor de archivos estáticos para producción. Instala dependencias con `pip install -r requirements.txt` y aplica los cambios de base de datos con `python manage.py migrate`.

La conexión MQTT usa TLS y lee sus credenciales solo del entorno: `MQTT_HOST` (por defecto, el broker HiveMQ del proyecto), `MQTT_PORT` (8883), `MQTT_USERNAME` y `MQTT_PASSWORD`. No guardes credenciales del broker en el repositorio. Cada planta recibe un identificador persistente formado por el nombre del cliente, la especie y un consecutivo, por ejemplo `ManuelSuculenta1` y `ManuelSuculenta2`. El comando de riego publica QoS 1 en `riego/plantas/{plant_id}/comandos`, con un JSON como `{"planta_id": "ManuelSuculenta1", "regar": true}`.

Ejecuta `python manage.py escuchar_mqtt` en un proceso persistente para recibir datos en `riego/plantas/{plant_id}/sensores`. El formato esperado es `{"temperatura": 23.5, "humedad": 61}`; también se aceptan las claves `temperature` y `humidity`. Los nombres de temas se pueden cambiar con `MQTT_COMMAND_TOPIC` y `MQTT_SENSOR_TOPIC`, conservando el marcador `{plant_id}` en el tema de sensores.