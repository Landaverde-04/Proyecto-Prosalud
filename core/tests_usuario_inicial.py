"""
La cuenta de arranque: la unica forma de entrar a un sistema recien
desplegado en un servidor sin consola.

Corre en cada arranque, asi que lo que mas importa aqui es que no vuelva a
tocar la cuenta una vez creada -- reescribir la contrasena en cada reinicio
seria una puerta abierta con la clave que quedo en el panel del servidor.
"""
from io import StringIO
from unittest import mock

from django.contrib.auth.models import Group
from django.core.management import call_command

from core.models import Clinica
from core.tests import PruebaCore
from seguridad.models import Usuario

VARIABLES = {'USUARIO_INICIAL': 'admin.inicial', 'PASSWORD_INICIAL': 'temporal-123'}


class CuentaDeArranqueTests(PruebaCore):

    def setUp(self):
        call_command('preparar_produccion', stdout=StringIO())

    def crear(self, **variables):
        with mock.patch.dict('os.environ', variables, clear=False):
            call_command('crear_usuario_inicial', stdout=StringIO())

    def test_sin_variables_no_crea_ninguna_cuenta(self):
        self.crear(USUARIO_INICIAL='', PASSWORD_INICIAL='')

        self.assertEqual(Usuario.objects.count(), 0)

    def test_crea_la_cuenta_con_rol_clinicas_y_cambio_de_contrasena(self):
        self.crear(**VARIABLES)

        usuario = Usuario.objects.get(username='admin.inicial')
        self.assertTrue(usuario.check_password('temporal-123'))
        self.assertTrue(usuario.debe_cambiar_password)
        self.assertEqual([g.name for g in usuario.groups.all()], ['Doctora Administradora'])
        self.assertEqual(usuario.clinicas.count(), Clinica.objects.count())
        # Es una cuenta de rol, no un superusuario que se salte los permisos.
        self.assertFalse(usuario.is_superuser)

    def test_si_la_cuenta_ya_existe_no_le_reescribe_la_contrasena(self):
        self.crear(**VARIABLES)
        usuario = Usuario.objects.get(username='admin.inicial')
        usuario.set_password('la-que-eligio-su-dueno')
        usuario.debe_cambiar_password = False
        usuario.save()

        self.crear(**VARIABLES)  # como en el siguiente arranque del servicio

        usuario.refresh_from_db()
        self.assertTrue(usuario.check_password('la-que-eligio-su-dueno'))
        self.assertFalse(usuario.debe_cambiar_password)
        self.assertEqual(Usuario.objects.count(), 1)

    def test_sin_el_rol_no_falla_el_arranque(self):
        """Un fallo aqui dejaria el servicio caido por una cuenta auxiliar."""
        Group.objects.filter(name='Doctora Administradora').delete()

        self.crear(**VARIABLES)

        self.assertEqual(Usuario.objects.count(), 0)
