from django.contrib.auth.models import Group, Permission
from django.urls import reverse

from core.models import Clinica
from core.tests import PruebaCore
from seguridad.models import Usuario

from .models import Contacto, Expediente, Persona


class RegistrarAdultoTests(PruebaCore):
    """
    HU-EXP-01: registrar paciente adulto con contacto de referencia.
    """

    def setUp(self):
        self.permiso_add_persona = Permission.objects.get(
            content_type__app_label='pacientes', codename='add_persona',
        )
        self.rol_enfermera = Group.objects.create(name='Enfermera')
        self.rol_enfermera.permissions.add(self.permiso_add_persona)
        self.rol_laboratorio = Group.objects.create(name='Laboratorio')

        self.enfermera = Usuario.objects.create_user(username='enfermera', password='clave123')
        self.enfermera.groups.add(self.rol_enfermera)

        self.laboratorio = Usuario.objects.create_user(username='laboratorio', password='clave123')
        self.laboratorio.groups.add(self.rol_laboratorio)

        self.url = reverse('pacientes:registrar_adulto')

        self.datos_base = {
            'nombres': 'Roberto Antonio',
            'apellidos': 'Guevara Peña',
            'fecha_nacimiento': '1993-06-15',
            'telefono': '7900-3344',
            'dui': '',
            'sexo': '',
            'contacto_persona_id': '',
            'contacto_nombres': 'Walter',
            'contacto_apellidos': 'Rivas Molina',
            'contacto_telefono': '7211-5567',
            'contacto_parentesco': Contacto.Parentesco.HERMANO,
            'contacto_parentesco_otro': '',
        }

    def test_enfermera_puede_acceder(self):
        self.client.force_login(self.enfermera)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)

    def test_sin_permiso_da_403(self):
        self.client.force_login(self.laboratorio)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 403)

    def test_registrar_crea_persona_contacto_y_expediente(self):
        self.client.force_login(self.enfermera)
        respuesta = self.client.post(self.url, self.datos_base)

        self.assertRedirects(respuesta, self.url)

        paciente = Persona.objects.get(nombres='Roberto Antonio')
        self.assertEqual(paciente.apellidos, 'Guevara Peña')
        self.assertEqual(paciente.creado_por, self.enfermera)

        contacto = Contacto.objects.get(paciente=paciente)
        self.assertEqual(contacto.tipo, Contacto.Tipo.REFERENCIA)
        self.assertEqual(contacto.persona_contacto.nombres, 'Walter')
        # El contacto nuevo no tiene fecha de nacimiento -- no se pide en HU-EXP-01.
        self.assertIsNone(contacto.persona_contacto.fecha_nacimiento)

        expediente = Expediente.objects.get(persona=paciente)
        self.assertEqual(expediente.clinica.nombre, 'ProSalud')

    def test_reutiliza_contacto_existente_en_vez_de_duplicar(self):
        self.client.force_login(self.enfermera)

        existente = Persona.objects.create(
            nombres='Carlos', apellidos='Hernandez Lopez', telefono='7845-1123',
        )

        datos = dict(self.datos_base)
        datos['contacto_persona_id'] = existente.pk

        self.client.post(self.url, datos)

        paciente = Persona.objects.get(nombres='Roberto Antonio')
        contacto = Contacto.objects.get(paciente=paciente)
        self.assertEqual(contacto.persona_contacto_id, existente.pk)
        # No se creo una segunda Persona "Carlos".
        self.assertEqual(Persona.objects.filter(nombres='Carlos').count(), 1)

    def test_no_guarda_con_contacto_incompleto(self):
        """A medias no vale: o se completa el contacto, o se deja todo vacío."""
        self.client.force_login(self.enfermera)
        datos = dict(self.datos_base)
        datos['contacto_nombres'] = ''
        datos['contacto_apellidos'] = ''
        datos['contacto_telefono'] = ''
        # contacto_parentesco sigue lleno (viene de datos_base) -> parcial.

        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)  # no redirige: no se guardo
        self.assertFalse(Persona.objects.filter(nombres='Roberto Antonio').exists())
        self.assertContains(respuesta, 'completa nombre, apellidos, teléfono y parentesco')

    def test_registra_paciente_sin_contacto(self):
        """El contacto es opcional: se puede omitir por completo."""
        self.client.force_login(self.enfermera)
        datos = dict(self.datos_base)
        datos['contacto_nombres'] = ''
        datos['contacto_apellidos'] = ''
        datos['contacto_telefono'] = ''
        datos['contacto_parentesco'] = ''

        respuesta = self.client.post(self.url, datos)

        self.assertRedirects(respuesta, self.url)
        paciente = Persona.objects.get(nombres='Roberto Antonio')
        self.assertFalse(Contacto.objects.filter(paciente=paciente).exists())

    def test_parentesco_otro_exige_detalle(self):
        self.client.force_login(self.enfermera)
        datos = dict(self.datos_base)
        datos['contacto_parentesco'] = Contacto.Parentesco.OTRO
        # contacto_parentesco_otro se deja vacio a proposito.

        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Especifica cuál es el parentesco')

    def test_parentesco_otro_guarda_el_detalle(self):
        self.client.force_login(self.enfermera)
        datos = dict(self.datos_base)
        datos['contacto_parentesco'] = Contacto.Parentesco.OTRO
        datos['contacto_parentesco_otro'] = 'Cuñado'

        self.client.post(self.url, datos)

        contacto = Contacto.objects.get(paciente__nombres='Roberto Antonio')
        self.assertEqual(contacto.parentesco, Contacto.Parentesco.OTRO)
        self.assertEqual(contacto.parentesco_mostrado, 'Cuñado')

    def test_parentesco_fuera_de_la_lista_no_es_valido(self):
        self.client.force_login(self.enfermera)
        datos = dict(self.datos_base)
        datos['contacto_parentesco'] = 'invento_que_no_existe'

        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Persona.objects.filter(nombres='Roberto Antonio').exists())

    def test_nombre_con_numeros_no_es_valido(self):
        self.client.force_login(self.enfermera)
        datos = dict(self.datos_base)
        datos['nombres'] = 'Roberto2'

        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Solo se permiten letras')
        self.assertFalse(Persona.objects.filter(apellidos='Guevara Peña').exists())

    def test_telefono_con_formato_invalido_no_es_valido(self):
        self.client.force_login(self.enfermera)
        datos = dict(self.datos_base)
        datos['telefono'] = '79003344'  # sin guion

        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'formato 0000-0000')

    def test_dui_con_formato_invalido_no_es_valido(self):
        self.client.force_login(self.enfermera)
        datos = dict(self.datos_base)
        datos['dui'] = '123456789'  # sin guion

        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'formato 00000000-0')

    def test_buscar_persona_encuentra_por_telefono(self):
        self.client.force_login(self.enfermera)
        Persona.objects.create(nombres='Carlos', apellidos='Hernandez Lopez', telefono='7845-1123')
        Persona.objects.create(nombres='Ana', apellidos='Lopez', telefono='7011-9988')

        respuesta = self.client.get(reverse('pacientes:buscar_persona'), {'q': '7845'})

        datos = respuesta.json()
        self.assertEqual(len(datos['resultados']), 1)
        self.assertEqual(datos['resultados'][0]['nombres'], 'Carlos')

    def test_buscar_persona_no_busca_con_menos_de_dos_caracteres(self):
        self.client.force_login(self.enfermera)
        Persona.objects.create(nombres='Carlos', apellidos='Hernandez Lopez', telefono='7845-1123')

        respuesta = self.client.get(reverse('pacientes:buscar_persona'), {'q': '7'})

        self.assertEqual(respuesta.json()['resultados'], [])

    def test_buscar_persona_encuentra_por_nombre_sin_importar_tildes(self):
        self.client.force_login(self.enfermera)
        Persona.objects.create(nombres='José', apellidos='Pérez', telefono='7011-2233')

        respuesta = self.client.get(reverse('pacientes:buscar_persona'), {'q': 'jose'})
        self.assertEqual(len(respuesta.json()['resultados']), 1)

        respuesta = self.client.get(reverse('pacientes:buscar_persona'), {'q': 'PEREZ'})
        self.assertEqual(len(respuesta.json()['resultados']), 1)


class ListaPacientesTests(PruebaCore):
    """
    HU-EXP-04, version parcial: solo el listado (sin buscador todavia).
    """

    def setUp(self):
        permiso_view = Permission.objects.get(
            content_type__app_label='pacientes', codename='view_persona',
        )
        self.rol_enfermera = Group.objects.create(name='Enfermera')
        self.rol_enfermera.permissions.add(permiso_view)
        self.rol_laboratorio = Group.objects.create(name='Laboratorio')

        self.enfermera = Usuario.objects.create_user(username='enfermera', password='clave123')
        self.enfermera.groups.add(self.rol_enfermera)

        self.laboratorio = Usuario.objects.create_user(username='laboratorio', password='clave123')
        self.laboratorio.groups.add(self.rol_laboratorio)

        self.url = reverse('pacientes:lista_pacientes')
        self.clinica = Clinica.objects.create(nombre='ProSalud')

    def test_enfermera_puede_ver_la_lista(self):
        self.client.force_login(self.enfermera)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)

    def test_sin_permiso_da_403(self):
        self.client.force_login(self.laboratorio)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 403)

    def test_solo_lista_personas_con_expediente(self):
        paciente = Persona.objects.create(nombres='Maria', apellidos='Perez', fecha_nacimiento='1990-01-01')
        Expediente.objects.create(persona=paciente, clinica=self.clinica)
        # Un contacto sin expediente propio no es "paciente" todavia.
        Persona.objects.create(nombres='Carlos', apellidos='Hernandez', fecha_nacimiento=None)

        self.client.force_login(self.enfermera)
        respuesta = self.client.get(self.url)

        nombres_mostrados = [p.nombres for p in respuesta.context['pagina'].object_list]
        self.assertIn('Maria', nombres_mostrados)
        self.assertNotIn('Carlos', nombres_mostrados)
        self.assertEqual(respuesta.context['total'], 1)
