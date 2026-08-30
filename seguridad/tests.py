from django.contrib.auth.models import Group, Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Usuario


# Las pruebas corren con DEBUG=False, y ahi el storage de WhiteNoise exige el
# manifiesto que genera 'collectstatic'. En pruebas no interesa el hash de los
# estaticos, solo que la plantilla se renderice, asi que se usa el storage
# simple de Django. Heredar de esta clase evita repetirlo en cada prueba nueva.
@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }
)
class PruebaSeguridad(TestCase):
    pass


class GuardaUltimoAdministradorTests(PruebaSeguridad):
    """
    Nadie debe poder dejar el sistema sin ningún usuario capaz de administrar
    roles. Si eso pasa, la única forma de recuperarlo es la consola del
    servidor -- justo lo que estas guardas evitan.

    Escenario base: 'doctora' es la única administradora y 'enfermera' no
    administra nada.
    """

    def setUp(self):
        perm_roles = Permission.objects.get(
            codename='change_group', content_type__app_label='auth'
        )
        perm_usuarios = Permission.objects.get(
            codename='change_usuario', content_type__app_label='seguridad'
        )
        perm_borrar_rol = Permission.objects.get(
            codename='delete_group', content_type__app_label='auth'
        )

        self.rol_admin = Group.objects.create(name='Doctora Administradora')
        self.rol_admin.permissions.add(perm_roles, perm_usuarios, perm_borrar_rol)

        self.rol_enfermera = Group.objects.create(name='Enfermera')

        self.doctora = Usuario.objects.create_user(username='doctora', password='x')
        self.doctora.groups.add(self.rol_admin)

        self.enfermera = Usuario.objects.create_user(username='enfermera', password='x')
        self.enfermera.groups.add(self.rol_enfermera)

        self.client.force_login(self.doctora)

    def _datos_edicion(self, usuario, **cambios):
        rol = usuario.groups.first()
        datos = {
            'username': usuario.username,
            'first_name': usuario.first_name,
            'last_name': usuario.last_name,
            'email': usuario.email,
            'is_active': 'on',
            'groups': str(rol.pk) if rol else '',
        }
        datos.update(cambios)
        return datos

    # --- Quitar el rol desde el formulario de usuario ---

    def test_no_puede_quitarse_el_rol_siendo_la_unica_administradora(self):
        respuesta = self.client.post(
            reverse('seguridad:editar_usuario', args=[self.doctora.pk]),
            self._datos_edicion(self.doctora, groups=''),
        )
        self.assertEqual(respuesta.status_code, 200)  # se queda en el formulario
        self.assertTrue(self.doctora.groups.filter(pk=self.rol_admin.pk).exists())

    def test_si_puede_quitarse_el_rol_cuando_hay_otra_administradora(self):
        self.enfermera.groups.set([self.rol_admin])

        respuesta = self.client.post(
            reverse('seguridad:editar_usuario', args=[self.doctora.pk]),
            self._datos_edicion(self.doctora, groups=''),
        )
        self.assertEqual(respuesta.status_code, 302)  # guardó y redirigió
        self.assertFalse(self.doctora.groups.exists())

    def test_no_puede_desactivarse_desde_el_formulario_siendo_la_unica(self):
        respuesta = self.client.post(
            reverse('seguridad:editar_usuario', args=[self.doctora.pk]),
            self._datos_edicion(self.doctora, is_active=''),
        )
        self.assertEqual(respuesta.status_code, 200)
        self.doctora.refresh_from_db()
        self.assertTrue(self.doctora.is_active)

    # --- Desactivar desde el botón de la lista ---

    def test_no_puede_desactivar_a_la_unica_administradora(self):
        # Quien desactiva es otra persona: puede editar usuarios pero no roles
        rol_operador = Group.objects.create(name='Operador')
        rol_operador.permissions.add(
            Permission.objects.get(
                codename='change_usuario', content_type__app_label='seguridad'
            )
        )
        operador = Usuario.objects.create_user(username='operador', password='x')
        operador.groups.add(rol_operador)
        self.client.force_login(operador)

        self.client.post(
            reverse('seguridad:cambiar_estado_usuario', args=[self.doctora.pk])
        )
        self.doctora.refresh_from_db()
        self.assertTrue(self.doctora.is_active)

    def test_nadie_puede_desactivar_su_propia_cuenta(self):
        self.enfermera.groups.set([self.rol_admin])  # para que no sea la última
        self.client.post(
            reverse('seguridad:cambiar_estado_usuario', args=[self.doctora.pk])
        )
        self.doctora.refresh_from_db()
        self.assertTrue(self.doctora.is_active)

    # --- Eliminar el rol que otorga la administración ---

    def test_no_puede_eliminar_el_unico_rol_que_administra(self):
        self.client.post(reverse('seguridad:eliminar_rol', args=[self.rol_admin.pk]))
        self.assertTrue(Group.objects.filter(pk=self.rol_admin.pk).exists())

    def test_si_puede_eliminar_un_rol_que_no_administra(self):
        self.client.post(reverse('seguridad:eliminar_rol', args=[self.rol_enfermera.pk]))
        self.assertFalse(Group.objects.filter(pk=self.rol_enfermera.pk).exists())

    # --- Quitar desde la pantalla "Usuarios del rol" ---

    def test_no_puede_quitar_del_rol_a_la_unica_administradora(self):
        self.client.post(
            reverse('seguridad:usuarios_rol', args=[self.rol_admin.pk]),
            {'accion': 'quitar', 'usuario_id': self.doctora.pk},
        )
        self.assertTrue(self.doctora.groups.filter(pk=self.rol_admin.pk).exists())


class RolUnicoTests(PruebaSeguridad):
    """Un usuario tiene un solo rol, por cualquiera de las dos pantallas."""

    def setUp(self):
        self.rol_a = Group.objects.create(name='Enfermera')
        self.rol_b = Group.objects.create(name='Laboratorio')

        admin_group = Group.objects.create(name='Admin')
        admin_group.permissions.add(
            Permission.objects.get(codename='change_group', content_type__app_label='auth'),
            Permission.objects.get(codename='change_usuario', content_type__app_label='seguridad'),
        )
        self.jefa = Usuario.objects.create_user(username='jefa', password='x')
        self.jefa.groups.add(admin_group)

        self.persona = Usuario.objects.create_user(username='persona', password='x')
        self.persona.groups.add(self.rol_a)

        self.client.force_login(self.jefa)

    def test_el_formulario_rechaza_dos_roles(self):
        respuesta = self.client.post(
            reverse('seguridad:editar_usuario', args=[self.persona.pk]),
            {
                'username': 'persona', 'first_name': '', 'last_name': '',
                'email': '', 'is_active': 'on',
                'groups': [str(self.rol_a.pk), str(self.rol_b.pk)],
            },
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(self.persona.groups.count(), 1)

    def test_asignar_desde_usuarios_del_rol_reemplaza_el_anterior(self):
        self.client.post(
            reverse('seguridad:usuarios_rol', args=[self.rol_b.pk]),
            {'accion': 'agregar', 'usuario_id': self.persona.pk},
        )
        self.assertEqual(
            list(self.persona.groups.values_list('name', flat=True)), ['Laboratorio']
        )


class AvisoSesionVencidaTests(PruebaSeguridad):
    """
    Al volver al login tras vencer la sesión por inactividad, el usuario debe
    entender por qué se le cerró. Igual de importante: NO debe avisarse cuando
    no corresponde (primera visita, o salida a propósito), o el aviso pierde
    sentido y confunde.
    """

    AVISO = 'Tu sesión se cerró por inactividad'

    def setUp(self):
        self.usuario = Usuario.objects.create_user(username='doctora', password='clave-de-prueba')
        self.url_login = reverse('seguridad:login')

    def _iniciar_sesion(self):
        self.client.post(self.url_login, {'username': 'doctora', 'password': 'clave-de-prueba'})

    def _vencer_sesion(self):
        """Simula inactividad: la sesión desaparece, pero la marca sobrevive."""
        self.client.cookies.pop('sessionid', None)

    def test_avisa_cuando_la_sesion_vencio(self):
        self._iniciar_sesion()
        self._vencer_sesion()
        respuesta = self.client.get(self.url_login)
        self.assertContains(respuesta, self.AVISO)

    def test_no_avisa_en_la_primera_visita(self):
        respuesta = self.client.get(self.url_login)
        self.assertNotContains(respuesta, self.AVISO)

    def test_no_avisa_tras_cerrar_sesion_a_proposito(self):
        self._iniciar_sesion()
        self.client.post(reverse('seguridad:logout'))
        respuesta = self.client.get(self.url_login)
        self.assertNotContains(respuesta, self.AVISO)

    def test_el_aviso_no_se_repite_al_recargar(self):
        self._iniciar_sesion()
        self._vencer_sesion()
        self.client.get(self.url_login)  # aquí sí avisa
        respuesta = self.client.get(self.url_login)
        self.assertNotContains(respuesta, self.AVISO)

    def test_la_marca_de_sesion_no_es_accesible_desde_javascript(self):
        self._iniciar_sesion()
        self.assertTrue(self.client.cookies['prosalud_sesion_previa']['httponly'])
