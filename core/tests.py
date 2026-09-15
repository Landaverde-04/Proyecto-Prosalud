from django.contrib.auth.models import Group, Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from seguridad.models import Usuario

from .models import RegistroAuditoria


# Mismo motivo que en seguridad/tests.py: las pruebas corren con DEBUG=False
# y el storage de WhiteNoise exige el manifiesto de 'collectstatic'.
@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }
)
class PruebaCore(TestCase):
    pass


class BitacoraRegistraAccionesTests(PruebaCore):
    """
    Las acciones sensibles no dejan rastro en ningún registro: resetear una
    contraseña no cambia ningún campo visible, y cambiar permisos de un rol
    tampoco. Si la bitácora no las captura, son invisibles.
    """

    def setUp(self):
        self.rol_admin = Group.objects.create(name='Doctora Administradora')
        self.rol_admin.permissions.set(
            Permission.objects.filter(
                codename__in=['change_group', 'view_group', 'change_usuario', 'add_usuario'],
            )
        )
        self.jefa = Usuario.objects.create_user(username='jefa', password='x')
        self.jefa.groups.add(self.rol_admin)

        self.otra = Usuario.objects.create_user(username='otra', password='x')

        self.client.force_login(self.jefa)

    def test_registra_el_reseteo_de_contrasena(self):
        self.client.post(
            reverse('seguridad:resetear_password', args=[self.otra.pk]),
            {'password1': 'ClaveLarga2026!', 'password2': 'ClaveLarga2026!'},
        )
        registro = RegistroAuditoria.objects.get(
            accion=RegistroAuditoria.Accion.RESETEAR_PASSWORD
        )
        self.assertEqual(registro.usuario_nombre, 'jefa')
        self.assertEqual(registro.objetivo, 'otra')

    def test_registra_la_desactivacion_de_un_usuario(self):
        self.client.post(reverse('seguridad:cambiar_estado_usuario', args=[self.otra.pk]))
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                accion=RegistroAuditoria.Accion.DESACTIVAR_USUARIO,
                objetivo='otra',
            ).exists()
        )

    def test_registra_que_permisos_se_le_agregaron_a_un_rol(self):
        """Lo más delicado: que quede constancia de qué permiso, no solo 'lo editó'."""
        rol = Group.objects.create(name='Enfermera')
        permisos = Permission.objects.filter(codename__in=['view_usuario', 'add_usuario'])
        self.client.post(
            reverse('seguridad:editar_rol', args=[rol.pk]),
            {'name': 'Enfermera', 'permissions': [str(p.pk) for p in permisos]},
        )
        registro = RegistroAuditoria.objects.get(accion=RegistroAuditoria.Accion.EDITAR_ROL)
        self.assertIn('Ver usuario', registro.detalle)
        self.assertIn('Agregar usuario', registro.detalle)

    def test_el_detalle_no_muestra_codenames_tecnicos(self):
        """
        La doctora no debe ver 'change_group' ni 'view_usuario' crudos -- eso
        no significa nada para alguien que no programa.
        """
        rol = Group.objects.create(name='Enfermera')
        permisos = Permission.objects.filter(codename__in=['view_usuario', 'change_group'])
        self.client.post(
            reverse('seguridad:editar_rol', args=[rol.pk]),
            {'name': 'Enfermera', 'permissions': [str(p.pk) for p in permisos]},
        )
        registro = RegistroAuditoria.objects.get(accion=RegistroAuditoria.Accion.EDITAR_ROL)
        self.assertNotIn('change_group', registro.detalle)
        self.assertNotIn('view_usuario', registro.detalle)

    def test_el_nombre_de_quien_actua_queda_congelado(self):
        """
        Si la persona cambia de nombre después, la bitácora debe seguir
        diciendo cómo se llamaba cuando hizo la acción.
        """
        self.client.post(reverse('seguridad:cambiar_estado_usuario', args=[self.otra.pk]))

        self.jefa.username = 'jefa_con_otro_nombre'
        self.jefa.save()

        registro = RegistroAuditoria.objects.first()
        self.assertEqual(registro.usuario_nombre, 'jefa')
        self.assertEqual(registro.usuario, self.jefa)


class BitacoraPantallaTests(PruebaCore):
    """La bitácora es información sensible: quién hizo qué y sobre quién."""

    def setUp(self):
        self.url = reverse('core:bitacora')
        self.espia = Usuario.objects.create_user(username='espia', password='x')
        self.auditora = Usuario.objects.create_user(username='auditora', password='x')
        self.auditora.user_permissions.add(
            Permission.objects.get(codename='view_registroauditoria')
        )
        RegistroAuditoria.objects.create(
            usuario=self.auditora, usuario_nombre='auditora',
            accion=RegistroAuditoria.Accion.CREAR_ROL, objetivo='Laboratorio',
        )

    def test_sin_permiso_no_se_puede_ver(self):
        self.client.force_login(self.espia)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_con_permiso_se_ve(self):
        self.client.force_login(self.auditora)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Laboratorio')

    def test_el_filtro_por_accion_descarta_lo_demas(self):
        self.client.force_login(self.auditora)
        respuesta = self.client.get(self.url, {'accion': RegistroAuditoria.Accion.ELIMINAR_ROL})
        self.assertNotContains(respuesta, 'Laboratorio')

    def test_la_paginacion_no_revienta_en_la_primera_ni_en_la_ultima_pagina(self):
        """
        previous_page_number y next_page_number lanzan excepción si no existe
        esa página. Llamarlos sin proteger tumbaba la primera y la última.
        """
        RegistroAuditoria.objects.bulk_create([
            RegistroAuditoria(
                usuario=self.auditora, usuario_nombre='auditora',
                accion=RegistroAuditoria.Accion.CREAR_ROL, objetivo=f'rol-{i}',
            )
            for i in range(60)
        ])
        self.client.force_login(self.auditora)
        for pagina in (1, 2, 3):
            with self.subTest(pagina=pagina):
                self.assertEqual(self.client.get(self.url, {'page': pagina}).status_code, 200)

    def test_la_paginacion_conserva_el_filtro(self):
        RegistroAuditoria.objects.bulk_create([
            RegistroAuditoria(
                usuario=self.auditora, usuario_nombre='auditora',
                accion=RegistroAuditoria.Accion.CREAR_ROL, objetivo=f'rol-{i}',
            )
            for i in range(60)
        ])
        self.client.force_login(self.auditora)
        respuesta = self.client.get(self.url, {'accion': RegistroAuditoria.Accion.CREAR_ROL})
        self.assertContains(respuesta, 'accion=crear_rol')


class InicioTests(PruebaCore):
    """Pantalla de inicio: cifras del dia, accesos y paneles segun los permisos del usuario."""

    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        from consultas.models import Consulta
        from core.models import Clinica
        from pacientes.models import Expediente, Persona

        def permisos(*nombres):
            return [Permission.objects.get(content_type__app_label=app, codename=codigo)
                    for app, codigo in (n.split('.') for n in nombres)]

        self.clinica = Clinica.objects.create(nombre='ProSalud')
        rol_enfermera = Group.objects.create(name='Enfermera')
        rol_enfermera.permissions.set(permisos(
            'pacientes.view_persona', 'pacientes.add_persona', 'consultas.view_consulta',
            'consultas.add_signosvitales', 'consultas.add_consulta'))
        rol_doctor = Group.objects.create(name='Doctor')
        rol_doctor.permissions.set(permisos(
            'pacientes.view_persona', 'pacientes.view_expediente', 'consultas.view_consulta',
            'consultas.change_consulta'))
        rol_admin = Group.objects.create(name='Doctora Administradora')
        rol_admin.permissions.set(permisos(
            'seguridad.view_usuario', 'auth.view_group', 'core.view_registroauditoria'))
        Group.objects.create(name='Laboratorio')

        def usuario(nombre, rol):
            u = Usuario.objects.create_user(username=nombre, password='x', first_name=nombre.capitalize())
            u.groups.add(Group.objects.get(name=rol))
            u.clinicas.add(self.clinica)
            return u

        self.enfermera = usuario('enfermera', 'Enfermera')
        self.doctor = usuario('doctor', 'Doctor')
        self.otro_doctor = usuario('otro', 'Doctor')
        self.admin = usuario('admin', 'Doctora Administradora')
        self.laboratorio = usuario('lab', 'Laboratorio')

        ahora = timezone.now()

        def consulta(nombre, doctor, **campos):
            persona = Persona.objects.create(nombres=nombre, apellidos='Prueba', fecha_nacimiento='1990-01-01')
            expediente = Expediente.objects.create(persona=persona, clinica=self.clinica)
            return Consulta.objects.create(expediente=expediente, doctor=doctor, motivo='x', **campos)

        consulta('EsperaMia', self.doctor, hora_llegada=ahora)
        consulta('EmergenciaMia', self.doctor, hora_llegada=ahora, es_emergencia=True, motivo_prioridad='Dolor')
        consulta('EsperaAjena', self.otro_doctor, hora_llegada=ahora)
        consulta('AtendidoHoy', self.doctor, inicio=ahora, cierre=ahora)
        consulta('Retirado', self.doctor, cierre=ahora, nota_retiro='Se fue')
        consulta('Ayer', self.doctor, inicio=ahora - timedelta(days=1), cierre=ahora - timedelta(days=1))
        self.url = reverse('core:home')

    def test_ya_no_muestra_bienvenida(self):
        self.client.force_login(self.enfermera)

        self.assertNotContains(self.client.get(self.url), 'Bienvenido')

    def test_enfermera_ve_cifras_de_toda_la_clinica_y_colas_por_medico(self):
        self.client.force_login(self.enfermera)

        respuesta = self.client.get(self.url)

        resumen = respuesta.context['resumen']
        self.assertFalse(resumen['solo_lo_suyo'])
        self.assertEqual(resumen['en_espera'], 3)
        self.assertEqual(resumen['emergencias'], 1)
        self.assertEqual({m.username: m.en_espera for m in resumen['colas']}, {'doctor': 2, 'otro': 1})
        self.assertIsNone(resumen['proximos'])
        self.assertContains(respuesta, 'Nuevo paciente')
        self.assertContains(respuesta, 'Colas por médico')
        self.assertNotContains(respuesta, reverse('seguridad:lista_usuarios'))

    def test_enfermera_no_ve_atendidos_ni_pacientes_nuevos_del_dia(self):
        self.client.force_login(self.enfermera)

        respuesta = self.client.get(self.url)

        self.assertIsNone(respuesta.context['resumen']['atendidos_hoy'])
        self.assertIsNone(respuesta.context['resumen']['nuevos_hoy'])
        self.assertNotContains(respuesta, 'Atendidos hoy')
        self.assertNotContains(respuesta, 'Pacientes nuevos hoy')

    def test_doctor_ve_solo_lo_suyo_y_sus_proximos_con_la_emergencia_primero(self):
        self.client.force_login(self.doctor)

        respuesta = self.client.get(self.url)

        resumen = respuesta.context['resumen']
        self.assertTrue(resumen['solo_lo_suyo'])
        self.assertEqual(resumen['en_espera'], 2)
        # Los retiros y lo de ayer no cuentan como atendidos hoy.
        self.assertEqual(resumen['atendidos_hoy'], 1)
        self.assertEqual(resumen['nuevos_hoy'], 6)
        self.assertContains(respuesta, 'Atendiste hoy')
        self.assertEqual([c.expediente.persona.nombres for c in resumen['proximos']], ['EmergenciaMia', 'EsperaMia'])
        self.assertIsNone(resumen['colas'])
        self.assertContains(respuesta, 'En tu cola')
        self.assertNotContains(respuesta, 'EsperaAjena')
        self.assertNotContains(respuesta, 'Nuevo paciente')

    def test_administracion_ve_sus_accesos(self):
        self.client.force_login(self.admin)

        respuesta = self.client.get(self.url)

        for url in ('seguridad:lista_usuarios', 'seguridad:lista_roles', 'core:bitacora'):
            self.assertContains(respuesta, reverse(url))
        self.assertIsNone(respuesta.context['resumen'])

    def test_puesto_sin_permisos_solo_ve_su_perfil_y_un_aviso(self):
        self.client.force_login(self.laboratorio)

        respuesta = self.client.get(self.url)

        self.assertEqual([s['titulo'] for s in respuesta.context['accesos']], ['Mi cuenta'])
        self.assertFalse(respuesta.context['hay_paneles'])
        self.assertContains(respuesta, 'todavía no tiene pantallas asignadas')
