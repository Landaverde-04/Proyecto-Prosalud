#!/usr/bin/env bash
# Lo que Render corre al construir el servicio web.
#
# Aqui NO se migra la base: el plan gratuito no tiene "pre-deploy command"
# (la etapa que Render recomienda para eso) y la red privada de la base no
# esta garantizada durante el build. Las migraciones van en el arranque,
# ver start.sh.
set -o errexit   # si un paso falla, no se sigue con los siguientes

pip install -r requirements.txt

# Junta los estaticos de todas las apps en staticfiles/, que es de donde
# los sirve WhiteNoise. Sin esto el sistema se ve sin CSS ni logos.
python manage.py collectstatic --noinput
