"""
Cuenta puente para poder entrar la primera vez.

Una base recien preparada tiene clinicas y roles, pero ningun usuario, y en
un servidor sin consola no hay forma de crear el primero: `createsuperuser`
necesita una terminal. Este comando lo resuelve leyendo dos variables de
entorno al arrancar.

Es una cuenta de arranque, no la de nadie: se entra con ella, se da de alta
al personal desde la pantalla de Usuarios y despues se desactiva. Por eso
nace con `debe_cambiar_password`: la contrasena que viaja en la variable
deja de servir en cuanto alguien entra.
"""
import os

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from core.models import Clinica
from seguridad.models import Usuario

ROL = 'Doctora Administradora'


class Command(BaseCommand):
    help = 'Crea la cuenta de arranque a partir de USUARIO_INICIAL y PASSWORD_INICIAL'

    def handle(self, *args, **opciones):
        nombre = os.environ.get('USUARIO_INICIAL', '').strip()
        password = os.environ.get('PASSWORD_INICIAL', '')

        # Sin variables no hay nada que hacer: es lo normal una vez que el
        # sistema ya tiene usuarios y se borraron del entorno.
        if not nombre or not password:
            self.stdout.write('Cuenta de arranque: sin variables, no se crea ninguna')
            return

        # Si ya existe NO se toca, y menos la contrasena: este comando corre
        # en cada arranque, y reescribirla desharia la que definio su dueño.
        if Usuario.objects.filter(username=nombre).exists():
            self.stdout.write(f'Cuenta de arranque: {nombre} ya existe, no se modifica')
            return

        rol = Group.objects.filter(name=ROL).first()
        if rol is None:
            # No se lanza error a proposito: este comando corre al arrancar y
            # un fallo aqui dejaria el servicio caido por una cuenta auxiliar.
            self.stdout.write(self.style.WARNING(
                f'Cuenta de arranque: no existe el rol "{ROL}", no se crea nada'))
            return

        usuario = Usuario.objects.create_user(
            username=nombre, password=password,
            first_name='Cuenta', last_name='de arranque',
        )
        usuario.debe_cambiar_password = True
        usuario.save(update_fields=['debe_cambiar_password'])
        usuario.groups.add(rol)
        usuario.clinicas.set(Clinica.objects.filter(activo=True))

        self.stdout.write(self.style.SUCCESS(
            f'Cuenta de arranque {nombre} creada con el rol {ROL}. '
            'Pide cambiar la contraseña al primer ingreso; '
            'desactivarla y borrar las variables cuando el personal ya esté dado de alta.'))
