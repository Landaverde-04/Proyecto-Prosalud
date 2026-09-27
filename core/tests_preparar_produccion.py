"""
El comando que deja lista una base de produccion.

Corre en cada arranque del servicio (no hay pre-deploy en el plan
gratuito), asi que lo que se prueba es sobre todo que sea repetible y que
no deshaga nada configurado a mano.
"""
from io import StringIO

from django.contrib.auth.models import Group
from django.core.management import call_command

from core.models import Clinica
from core.tests import PruebaCore


class PrepararProduccionTests(PruebaCore):

    def preparar(self):
        call_command('preparar_produccion', stdout=StringIO())

    def test_deja_las_dos_clinicas_configuradas(self):
        self.preparar()

        estetica = Clinica.objects.get(tipo=Clinica.Tipo.ESTETICA)
        prosalud = Clinica.objects.get(tipo=Clinica.Tipo.MEDICA)
        self.assertEqual(Clinica.objects.count(), 2)
        self.assertFalse(estetica.usa_cola)
        self.assertEqual(estetica.nombre_corto, 'Estética')
        self.assertTrue(prosalud.usa_cola)
        self.assertTrue(prosalud.logo)

    def test_crea_los_seis_roles_con_sus_permisos(self):
        self.preparar()

        self.assertEqual(Group.objects.count(), 6)
        codigos = lambda rol: {p.codename for p in Group.objects.get(name=rol).permissions.all()}
        # La administradora lleva el catalogo completo.
        self.assertIn('change_group', codigos('Doctora Administradora'))
        self.assertIn('view_adjunto', codigos('Doctora Administradora'))
        # El doctor emite documentos y sube adjuntos, pero no los retira.
        self.assertIn('add_receta', codigos('Doctor'))
        self.assertIn('add_adjunto', codigos('Doctor'))
        self.assertNotIn('change_adjunto', codigos('Doctor'))
        # Enfermeria no abre expedientes; la secretaria solo registra y busca.
        self.assertNotIn('view_expediente', codigos('Enfermera'))
        self.assertEqual(codigos('Secretaria'), {'view_persona', 'add_persona'})

    def test_no_crea_usuarios_ni_pacientes(self):
        from pacientes.models import Persona
        from seguridad.models import Usuario

        self.preparar()

        self.assertEqual(Usuario.objects.count(), 0)
        self.assertEqual(Persona.objects.count(), 0)

    def test_correrlo_dos_veces_no_duplica_nada(self):
        self.preparar()
        self.preparar()

        self.assertEqual(Clinica.objects.count(), 2)
        self.assertEqual(Group.objects.count(), 6)

    def test_no_deshace_los_permisos_ajustados_a_mano(self):
        """Corre en cada arranque: no puede pisar lo que alguien configuro."""
        self.preparar()
        rol = Group.objects.get(name='Secretaria')
        rol.permissions.clear()

        self.preparar()

        self.assertEqual(rol.permissions.count(), 0)
