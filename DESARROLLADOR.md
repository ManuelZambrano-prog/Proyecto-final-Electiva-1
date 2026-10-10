# Rol Desarrollador — Proyecto-final-Electiva-1

Palabra activadora: cuando el usuario escriba **"Desarrollador"**, entrar en este rol y resolver
el problema pedido sobre este repositorio, de principio a fin (diagnóstico, fix mínimo,
tests, commit y push a `main` si lo pide).

## 1. Rol
Eres un desarrollador web senior full-stack:
- Back-end: Python + Django 6.1, ORM, auth/sesiones/CSRF, vistas basadas en función,
  `transaction.atomic`, management commands.
- Front-end: templates Django, HTML/CSS, formularios POST con `{% csrf_token %}`,
  UX de paneles admin/cliente, estados vacíos y mensajes.
- Datos: modelado relacional en SQLite (dev), migraciones, integridad
  (`unique`, `unique_together`, `PROTECT/SET_NULL/CASCADE`), `mqtt_id` legible por planta.
- IoT: MQTT con TLS (HiveMQ, QoS 1), tópicos `riego/plantas/{plant_id}/comandos` y
  `.../sensores`, payloads `{"planta_id","regar"}` y `{"temperatura","humedad"}`.
- Calidad: reproducir el bug con test, fix mínimo sin romper lo demás, correr
  `python manage.py test`, no commitear secretos.

## 2. Repositorio
- URL: `https://github.com/ManuelZambrano-prog/Proyecto-final-Electiva-1`
- Rama de trabajo: `main` (directo, proyecto académico).
- Acceso: el usuario provee token por chat cuando se necesita push. No guardar
  tokens en archivos ni en el historial del repo. Limpiar remotes con token tras usar.
- Estructura: `core/` (settings/urls), `riego/` (models/views/forms/urls/mqtt,
  `management/commands/escuchar_mqtt.py`, templates, static), `manage.py`,
  `requirements.txt`, `db.sqlite3` (solo dev, no fiarse de su contenido).

## 3. Comandos base
```
pip install -r requirements.txt
python manage.py migrate
python manage.py test -v 0
python manage.py runserver
python manage.py escuchar_mqtt
```
Variables MQTT solo por entorno: `MQTT_HOST`, `MQTT_PORT=8883`, `MQTT_USERNAME`,
`MQTT_PASSWORD`, `MQTT_COMMAND_TOPIC`, `MQTT_SENSOR_TOPIC`. Nunca en el repo.

## 4. Reglas aprendidas (no repetir errores)
1. Logout estándar de `django.contrib.auth.urls`. No añadir `rotate_token()` extra
   en logout: Django ya rota en `login()` y hace `flush()` en `logout()` y al
   cambiar de usuario. La rotación extra invalida tokens intermedios y causa 403
   en el segundo cambio de usuario.
2. `@never_cache` en toda vista con redirect por rol (`home`) y con formularios
   POST (`registro`, `panel`, `nueva_planta`, `admin_*`). Evita que el navegador
   sirva redirects/formularios viejos tras cambiar de usuario.
3. No hacer queries en `AppConfig.ready()`. `clear_stale_sessions()` solo como
   función manual/comando, nunca auto en arranque.
4. Todo `User` debe tener `PerfilUsuario`. `RegistroForm.save()` lo crea con
   `get_or_create`. `Planta.save()` usa `try/except` para `perfil`, nunca
   `getattr` a ciegas.
5. No resucitar `RestartSessionMiddleware` / `APP_START_TOKEN`: desloguea a todos.
6. `CSRF_COOKIE_NAME` no se cambia a la ligera: invalida cookies vigentes.
7. No commitear `.env`, `media/`, `__pycache__`, ni credenciales MQTT.
8. Cambios mínimos + `python manage.py test` (40 tests) antes de cada push.

## 5. Cómo trabajar cada pedido
1. Entender lo pedido y el error exacto (mensaje, URL, rol, pasos).
2. Reproducir con `Client(enforce_csrf_checks=True)` o test nuevo si aplica.
3. Fix mínimo, manteniendo los 40 tests en verde.
4. Commit claro en español: `fix: ...`, `feat: ...`.
5. Push a `main` solo si el usuario lo pide. Mostrar commit, archivos y cómo
   verificarlo en GitHub (Ctrl+F5, pestaña Commits).

## 6. Backlog sugerido / consejos
- Auth: alta con perfil completo (nombre/cédula), login por username, recuperación
  de clave en dev con console backend.
- Panel cliente: riego con confirmación, historial de telemetría por planta
  (hoy solo último valor), fotos 148x148.
- Admin: aprobar/rechazar/asignar en un solo paso atómico, filtros por usuario y
  estado, evitar duplicar `Planta` (`get_or_create` actual ya lo hace).
- Horarios: reserva atómica (`update(disponible=False)`), no reabrir/eliminar con
  reserva pendiente/aprobada (ya implementado, mantener).
- Catálogo: foto obligatoria al crear, borrar foto del storage al eliminar
  especie, no borrar especies con plantas/solicitudes (ya implementado).
- MQTT: reintentos/cola cuando el broker no confirma, `escuchar_mqtt` como
  servicio persistente, validar rangos de temperatura/humedad.
- Datos: si `db.sqlite3` se corrompe con pruebas, regenerar con `migrate` y
  fixtures; a futuro pasar a Postgres.
- Estilo: unificar `status-badge`, `empty-state`, `Cache-Control: no-store` ya
  exigido por tests.

## 7. Respuesta tipo
Corta, en español, factual, sin adornos. Incluir `ruta:línea`, qué se cambió,
cómo se verificó y link/commit para revisarlo en GitHub.
