from datetime import date, timedelta

from django.contrib.auth.models import Group, Permission
from django.urls import reverse

from core.models import Clinica
from core.tests import PruebaCore
from seguridad.models import Usuario

from .models import Contacto, Expediente, Persona


class RegistrarPacienteTests(PruebaCore):
    """
    HU-EXP-01 (adulto con contacto de referencia) y HU-EXP-02 (menor de
    edad con responsable) -- comparten formulario, vista y URL.
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

        self.url = reverse('pacientes:registrar_paciente')

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

    def test_fecha_de_nacimiento_futura_no_es_valida(self):
        self.client.force_login(self.enfermera)
        datos = dict(self.datos_base)
        datos['fecha_nacimiento'] = str(date.today() + timedelta(days=1))

        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Persona.objects.filter(nombres='Roberto Antonio').exists())
        self.assertContains(respuesta, 'no puede ser en el futuro')

    def test_dui_duplicado_no_guarda(self):
        self.client.force_login(self.enfermera)
        Persona.objects.create(nombres='Carlos', apellidos='Hernandez', dui='12345678-9')
        datos = dict(self.datos_base)
        datos['dui'] = '12345678-9'

        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Persona.objects.filter(nombres='Roberto Antonio').exists())
        self.assertContains(respuesta, 'Ya existe una persona registrada con este DUI')

    def test_paciente_duplicado_por_nombre_y_telefono_no_guarda(self):
        """El mismo caso que se vio en producción: el mismo paciente registrado dos veces."""
        self.client.force_login(self.enfermera)
        Persona.objects.create(nombres='Roberto Antonio', apellidos='Guevara Peña', telefono='7900-3344')

        respuesta = self.client.post(self.url, self.datos_base)

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Persona.objects.filter(nombres='Roberto Antonio').count(), 1)  # no se duplico
        self.assertContains(respuesta, 'Ya existe una persona registrada como')

    def test_contacto_nuevo_duplicado_por_nombre_y_telefono_no_guarda(self):
        self.client.force_login(self.enfermera)
        Persona.objects.create(nombres='Walter', apellidos='Rivas Molina', telefono='7211-5567')

        respuesta = self.client.post(self.url, self.datos_base)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Persona.objects.filter(nombres='Roberto Antonio').exists())
        self.assertEqual(Persona.objects.filter(nombres='Walter').count(), 1)  # no se duplico
        self.assertContains(respuesta, 'búscala arriba en vez de crearla de nuevo')

    def test_buscar_persona_encuentra_por_telefono(self):
        self.client.force_login(self.enfermera)
        Persona.objects.create(nombres='Carlos', apellidos='Hernandez Lopez', telefono='7845-1123')
        Persona.objects.create(nombres='Ana', apellidos='Lopez', telefono='7011-9988')

        respuesta = self.client.get(reverse('pacientes:buscar_persona'), {'q': '7845'})

        datos = respuesta.json()
        self.assertEqual(len(datos['resultados']), 1)
        self.assertEqual(datos['resultados'][0]['nombres'], 'Carlos')

    def test_buscar_persona_encuentra_telefono_sin_guion(self):
        self.client.force_login(self.enfermera)
        Persona.objects.create(nombres='Carlos', apellidos='Hernandez Lopez', telefono='7845-1123')

        respuesta = self.client.get(reverse('pacientes:buscar_persona'), {'q': '78451123'})

        datos = respuesta.json()['resultados']
        self.assertEqual(len(datos), 1)
        self.assertEqual(datos[0]['nombres'], 'Carlos')

    def test_buscar_persona_encuentra_dui_sin_guion(self):
        self.client.force_login(self.enfermera)
        Persona.objects.create(nombres='Carlos', apellidos='Hernandez Lopez', dui='12345678-9')

        respuesta = self.client.get(reverse('pacientes:buscar_persona'), {'q': '123456789'})

        datos = respuesta.json()['resultados']
        self.assertEqual(len(datos), 1)
        self.assertEqual(datos[0]['nombres'], 'Carlos')

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

    def test_buscar_persona_encuentra_por_nombre_completo(self):
        """Buscar "nombre apellido" junto debe encontrar, aunque esas dos
        palabras esten repartidas en dos columnas distintas (nombres/apellidos)."""
        self.client.force_login(self.enfermera)
        Persona.objects.create(nombres='Samuel', apellidos='Manzano', telefono='0000-0000')
        Persona.objects.create(nombres='Ana', apellidos='Lopez', telefono='7011-9988')

        respuesta = self.client.get(reverse('pacientes:buscar_persona'), {'q': 'samuel manzano'})

        datos = respuesta.json()['resultados']
        self.assertEqual(len(datos), 1)
        self.assertEqual(datos[0]['nombres'], 'Samuel')

    # ---- HU-EXP-02: registrar paciente menor de edad con responsable ----

    def _datos_menor(self, **cambios):
        """Mismos datos base, pero con fecha de nacimiento de un menor
        y el bloque de contacto jugando el papel de responsable."""
        datos = dict(self.datos_base)
        datos.update({
            'nombres': 'Diego Alejandro',
            'apellidos': 'Guevara Peña',
            'fecha_nacimiento': '2015-03-10',  # menor de edad hoy
            'dui': '',
            'contacto_nombres': 'Roberto Antonio',
            'contacto_apellidos': 'Guevara Peña',
            'contacto_telefono': '7900-3344',
            'contacto_parentesco': Contacto.Parentesco.PADRE_MADRE,
        })
        datos.update(cambios)
        return datos

    def test_registrar_menor_crea_responsable(self):
        self.client.force_login(self.enfermera)
        respuesta = self.client.post(self.url, self._datos_menor())

        self.assertRedirects(respuesta, self.url)
        paciente = Persona.objects.get(nombres='Diego Alejandro')
        contacto = Contacto.objects.get(paciente=paciente)
        # Diferencia clave con el adulto: el tipo es RESPONSABLE, no REFERENCIA.
        self.assertEqual(contacto.tipo, Contacto.Tipo.RESPONSABLE)
        self.assertEqual(contacto.persona_contacto.nombres, 'Roberto Antonio')

    def test_menor_puede_guardarse_sin_dui(self):
        self.client.force_login(self.enfermera)
        respuesta = self.client.post(self.url, self._datos_menor(dui=''))
        self.assertRedirects(respuesta, self.url)
        self.assertTrue(Persona.objects.filter(nombres='Diego Alejandro', dui='').exists())

    def test_menor_puede_guardarse_sin_telefono_propio(self):
        """Un niño normalmente no tiene teléfono propio -- solo el del responsable es obligatorio."""
        self.client.force_login(self.enfermera)
        respuesta = self.client.post(self.url, self._datos_menor(telefono=''))
        self.assertRedirects(respuesta, self.url)
        self.assertTrue(Persona.objects.filter(nombres='Diego Alejandro', telefono='').exists())

    def test_adulto_sin_telefono_no_guarda(self):
        """Para un adulto el teléfono propio sigue siendo obligatorio (HU-EXP-01)."""
        self.client.force_login(self.enfermera)
        datos = dict(self.datos_base)
        datos['telefono'] = ''
        respuesta = self.client.post(self.url, datos)
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Persona.objects.filter(nombres='Roberto Antonio').exists())
        self.assertContains(respuesta, 'El teléfono es obligatorio para pacientes adultos')

    def test_menor_sin_responsable_no_guarda(self):
        """A diferencia del adulto, el menor SI exige el bloque completo."""
        self.client.force_login(self.enfermera)
        datos = self._datos_menor(
            contacto_nombres='', contacto_apellidos='',
            contacto_telefono='', contacto_parentesco='',
        )
        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)  # no redirige: no se guardo
        self.assertFalse(Persona.objects.filter(nombres='Diego Alejandro').exists())
        self.assertContains(respuesta, 'necesitan un responsable')

    def test_menor_con_responsable_incompleto_no_guarda(self):
        self.client.force_login(self.enfermera)
        datos = self._datos_menor(contacto_telefono='')  # a medias
        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Persona.objects.filter(nombres='Diego Alejandro').exists())
        self.assertContains(respuesta, 'nombre, apellidos, teléfono y parentesco completos')

    def test_mismo_responsable_para_varios_pacientes(self):
        """HU-EXP-02: un mismo responsable puede estar asociado a varios pacientes (hermanos)."""
        self.client.force_login(self.enfermera)
        self.client.post(self.url, self._datos_menor())
        responsable = Persona.objects.get(nombres='Roberto Antonio', apellidos='Guevara Peña')

        # Segundo hijo, reutilizando al mismo responsable por su id.
        datos_hermano = self._datos_menor(
            nombres='Camila', apellidos='Guevara Peña',
            fecha_nacimiento='2018-07-01',
            contacto_persona_id=responsable.pk,
        )
        respuesta = self.client.post(self.url, datos_hermano)

        self.assertRedirects(respuesta, self.url)
        self.assertEqual(Contacto.objects.filter(persona_contacto=responsable).count(), 2)
        # No se duplico la Persona del responsable.
        self.assertEqual(Persona.objects.filter(nombres='Roberto Antonio').count(), 1)

    def test_ignora_interruptor_manipulado_y_usa_fecha_real(self):
        """
        El interruptor Adulto/Menor de la pantalla no es un campo del
        formulario -- el backend decide con la fecha de nacimiento real.
        Se simula un cliente que manda una fecha de adulto pero deja el
        contacto vacio (valido para adulto, invalido para menor): si el
        servidor confiara en un interruptor manipulado diria "menor" y
        lo rechazaria; como no existe tal campo, se procesa como adulto.
        """
        self.client.force_login(self.enfermera)
        datos = dict(self.datos_base)  # fecha_nacimiento de 1993, adulto
        datos.update({
            'tipo_paciente_ui': 'tipo-menor',  # no es un campo real del form
            'contacto_nombres': '', 'contacto_apellidos': '',
            'contacto_telefono': '', 'contacto_parentesco': '',
        })

        respuesta = self.client.post(self.url, datos)

        self.assertRedirects(respuesta, self.url)  # se guarda como adulto, sin exigir responsable
        paciente = Persona.objects.get(nombres='Roberto Antonio')
        self.assertFalse(Contacto.objects.filter(paciente=paciente).exists())


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
