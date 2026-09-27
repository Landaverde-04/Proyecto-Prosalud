#!/usr/bin/env bash
# Lo que Render corre al arrancar el servicio web.
#
# Migrar aqui y no en el build es a proposito: en el arranque la base si
# esta accesible por la red privada, y el plan gratuito no ofrece el
# "pre-deploy command" que seria el lugar natural. Ambos pasos son
# repetibles, asi que no molesta que corran en cada arranque.
set -o errexit

python manage.py migrate --noinput

# Crea las clinicas y los roles si faltan. Nunca modifica los que ya
# existen, para no deshacer ajustes hechos desde la pantalla de Roles.
python manage.py preparar_produccion

# Dos procesos: con 512 MB de RAM en el servicio y 256 MB en la base, mas
# procesos solo significan mas conexiones abiertas y menos memoria libre.
exec gunicorn sistema_prosalud.wsgi:application \
    --bind 0.0.0.0:"${PORT:-8000}" \
    --workers 2 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -
