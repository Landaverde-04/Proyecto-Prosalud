from datetime import date, timedelta

from django.contrib.auth.models import Group, Permission
from django.urls import reverse

from consultas.models import Consulta, SignosVitales
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
    HU-EXP-04: listado con buscador en vivo (mismo patron que Usuarios/
    Roles/Bitacora). "Seleccionar" (abrir expediente) y el caso
    cross-clinica quedan pendientes -- ver el docstring de la vista.
    """

    def setUp(self):
        # En la realidad, Enfermera tiene los dos permisos (ver la
        # lista y registrar pacientes) -- se otorgan ambos aqui para
        # que la prueba refleje el caso real, no un rol recortado.
        permiso_view = Permission.objects.get(
            content_type__app_label='pacientes', codename='view_persona',
        )
        permiso_add = Permission.objects.get(
            content_type__app_label='pacientes', codename='add_persona',
        )
        self.rol_enfermera = Group.objects.create(name='Enfermera')
        self.rol_enfermera.permissions.add(permiso_view, permiso_add)
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

    def _crear_paciente_con_expediente(self, **datos):
        paciente = Persona.objects.create(**datos)
        Expediente.objects.create(persona=paciente, clinica=self.clinica)
        return paciente

    def test_busca_por_nombre_completo(self):
        self._crear_paciente_con_expediente(
            nombres='Roberto Antonio', apellidos='Guevara Peña', fecha_nacimiento='1993-06-15',
        )
        self.client.force_login(self.enfermera)

        respuesta = self.client.get(self.url, {'q': 'roberto guevara'})

        nombres_mostrados = [p.nombres for p in respuesta.context['pagina'].object_list]
        self.assertIn('Roberto Antonio', nombres_mostrados)

    def test_busca_por_dui_propio_sin_guion(self):
        self._crear_paciente_con_expediente(
            nombres='Roberto Antonio', apellidos='Guevara Peña',
            fecha_nacimiento='1993-06-15', dui='11122233-4',
        )
        self.client.force_login(self.enfermera)

        respuesta = self.client.get(self.url, {'q': '111222334'})

        nombres_mostrados = [p.nombres for p in respuesta.context['pagina'].object_list]
        self.assertIn('Roberto Antonio', nombres_mostrados)

    def test_busca_por_telefono_propio_sin_guion(self):
        self._crear_paciente_con_expediente(
            nombres='Roberto Antonio', apellidos='Guevara Peña',
            fecha_nacimiento='1993-06-15', telefono='7900-3344',
        )
        self.client.force_login(self.enfermera)

        respuesta = self.client.get(self.url, {'q': '79003344'})

        nombres_mostrados = [p.nombres for p in respuesta.context['pagina'].object_list]
        self.assertIn('Roberto Antonio', nombres_mostrados)

    def test_busca_por_dui_del_responsable(self):
        paciente = self._crear_paciente_con_expediente(
            nombres='Diego', apellidos='Guevara Peña', fecha_nacimiento='2015-03-10',
        )
        responsable = Persona.objects.create(
            nombres='Roberto Antonio', apellidos='Guevara Peña', dui='55566677-8',
        )
        Contacto.objects.create(
            paciente=paciente, persona_contacto=responsable,
            tipo=Contacto.Tipo.RESPONSABLE, parentesco=Contacto.Parentesco.PADRE_MADRE,
        )
        self.client.force_login(self.enfermera)

        respuesta = self.client.get(self.url, {'q': '555666778'})

        nombres_mostrados = [p.nombres for p in respuesta.context['pagina'].object_list]
        self.assertIn('Diego', nombres_mostrados)

    def test_paciente_con_dos_contactos_no_aparece_duplicado(self):
        """
        Bug real encontrado al sembrar datos con HU-EXP-05 (un paciente
        puede tener mas de un contacto): anotar 'contactos__persona_
        contacto__dui' directamente hace un JOIN que multiplica la fila
        del paciente una vez por cada Contacto -- aparecia dos veces en
        la lista y en el conteo. Se corrigio con una subconsulta
        Exists(), que no se une a la consulta principal.
        """
        paciente = self._crear_paciente_con_expediente(
            nombres='Jose Roberto', apellidos='Munoz Castro', fecha_nacimiento='1975-11-30',
        )
        contacto_1 = Persona.objects.create(nombres='Gloria', apellidos='Castro', dui='11111111-1')
        contacto_2 = Persona.objects.create(nombres='Josue', apellidos='Manzano', dui='22222222-2')
        Contacto.objects.create(
            paciente=paciente, persona_contacto=contacto_1,
            tipo=Contacto.Tipo.REFERENCIA, parentesco=Contacto.Parentesco.HERMANO,
        )
        Contacto.objects.create(
            paciente=paciente, persona_contacto=contacto_2,
            tipo=Contacto.Tipo.REFERENCIA, parentesco=Contacto.Parentesco.VECINO,
        )
        self.client.force_login(self.enfermera)

        respuesta_sin_busqueda = self.client.get(self.url)
        self.assertEqual(respuesta_sin_busqueda.context['total'], 1)

        respuesta_buscando = self.client.get(self.url, {'q': 'jose roberto munoz'})
        self.assertEqual(len(respuesta_buscando.context['pagina'].object_list), 1)

        respuesta_por_dui = self.client.get(self.url, {'q': '111111111'})
        self.assertEqual(len(respuesta_por_dui.context['pagina'].object_list), 1)

    def test_paciente_que_tambien_es_contacto_de_otro_se_indica(self):
        """Si una Persona es paciente Y ademas es contacto/responsable de
        otro paciente, aparece una sola vez, con la relacion indicada."""
        hijo = self._crear_paciente_con_expediente(
            nombres='Diego', apellidos='Guevara Peña', fecha_nacimiento='2015-03-10',
        )
        mama = self._crear_paciente_con_expediente(
            nombres='Roberto Antonio', apellidos='Guevara Peña', fecha_nacimiento='1993-06-15',
            telefono='7900-3344',
        )
        Contacto.objects.create(
            paciente=hijo, persona_contacto=mama,
            tipo=Contacto.Tipo.RESPONSABLE, parentesco=Contacto.Parentesco.PADRE_MADRE,
        )
        self.client.force_login(self.enfermera)

        respuesta = self.client.get(self.url, {'q': 'roberto antonio guevara'})

        resultados = list(respuesta.context['pagina'].object_list)
        # Aparece una sola vez, no duplicada por el join con Contacto.
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].tambien_contacto_de, [hijo])

    def test_sin_resultados_ofrece_registrar_nuevo(self):
        self.client.force_login(self.enfermera)

        respuesta = self.client.get(self.url, {'q': 'nadie con este nombre'})

        self.assertContains(respuesta, 'No se encontraron pacientes')
        self.assertContains(respuesta, 'Registrar paciente nuevo')

    def test_fila_no_es_clicable_sin_permiso_de_ver_expediente(self):
        """Enfermera ve la lista, pero sus filas no deben ofrecer abrir el expediente."""
        self._crear_paciente_con_expediente(
            nombres='Roberto Antonio', apellidos='Guevara Peña', fecha_nacimiento='1993-06-15',
        )
        self.client.force_login(self.enfermera)

        respuesta = self.client.get(self.url)

        self.assertNotContains(respuesta, 'pacientes/expediente/')


class VerExpedienteTests(PruebaCore):
    """
    HU-EXP-05 (cabecera con datos preclinicos) y HU-EXP-06 (panel de
    tarjetas), una sola vista. Solo quien tiene 'pacientes.view_expediente'
    entra, y solo si el expediente pertenece a una clinica del usuario.
    """

    def setUp(self):
        permiso_view_expediente = Permission.objects.get(
            content_type__app_label='pacientes', codename='view_expediente',
        )
        self.rol_doctor = Group.objects.create(name='Doctor')
        self.rol_doctor.permissions.add(permiso_view_expediente)
        self.rol_enfermera = Group.objects.create(name='Enfermera')

        self.clinica = Clinica.objects.create(nombre='ProSalud')
        self.otra_clinica = Clinica.objects.create(nombre='Estética')

        self.doctor = Usuario.objects.create_user(username='doctor', password='clave123')
        self.doctor.groups.add(self.rol_doctor)
        self.doctor.clinicas.add(self.clinica)

        self.enfermera = Usuario.objects.create_user(username='enfermera', password='clave123')
        self.enfermera.groups.add(self.rol_enfermera)

        self.paciente = Persona.objects.create(
            nombres='Roberto Antonio', apellidos='Guevara Peña',
            fecha_nacimiento='1993-06-15', dui='11122233-4', telefono='7900-3344',
        )
        self.expediente = Expediente.objects.create(persona=self.paciente, clinica=self.clinica)
        self.url = reverse('pacientes:ver_expediente', args=[self.expediente.id])

    def test_doctor_puede_ver_expediente_de_su_clinica(self):
        self.client.force_login(self.doctor)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Roberto Antonio Guevara Peña')

    def test_enfermera_sin_permiso_da_403(self):
        self.client.force_login(self.enfermera)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 403)

    def test_doctor_de_otra_clinica_da_403(self):
        """El expediente existe, pero no en una clinica del usuario -- 403, no 404."""
        self.doctor.clinicas.set([self.otra_clinica])
        self.client.force_login(self.doctor)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 403)

    def test_expediente_inexistente_da_404(self):
        self.client.force_login(self.doctor)
        respuesta = self.client.get(reverse('pacientes:ver_expediente', args=[999999]))
        self.assertEqual(respuesta.status_code, 404)

    def test_cabecera_muestra_dui_cuando_lo_tiene(self):
        self.client.force_login(self.doctor)
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, '11122233-4')

    def test_cabecera_muestra_datos_del_responsable_si_no_tiene_dui(self):
        menor = Persona.objects.create(
            nombres='Diego', apellidos='Guevara Peña', fecha_nacimiento='2015-03-10',
        )
        responsable = Persona.objects.create(
            nombres='Roberto Antonio', apellidos='Guevara Peña', telefono='7900-3344',
        )
        Contacto.objects.create(
            paciente=menor, persona_contacto=responsable,
            tipo=Contacto.Tipo.RESPONSABLE, parentesco=Contacto.Parentesco.PADRE_MADRE,
        )
        expediente_menor = Expediente.objects.create(persona=menor, clinica=self.clinica)
        self.client.force_login(self.doctor)

        respuesta = self.client.get(reverse('pacientes:ver_expediente', args=[expediente_menor.id]))

        self.assertContains(respuesta, 'Sin DUI (menor de edad)')
        self.assertContains(respuesta, 'Roberto Antonio Guevara Peña')

    def test_cabecera_indica_que_no_hay_datos_de_preconsulta(self):
        """SignosVitales todavia no existe (HU-EXP-09, despues de agosto) -- siempre "sin datos" por ahora."""
        self.client.force_login(self.doctor)
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, 'No hay datos de preconsulta registrados')


class AgregarContactoTests(PruebaCore):
    """
    Agregar un responsable/contacto adicional desde el expediente ya
    abierto -- la decision que quedo pendiente en HU-EXP-02 (05/09/2026)
    para cuando existiera esta pantalla (HU-EXP-05/06). Mismo permiso
    que ver_expediente: la accion vive dentro del expediente, no es un
    punto de entrada aparte.
    """

    def setUp(self):
        permiso_view_expediente = Permission.objects.get(
            content_type__app_label='pacientes', codename='view_expediente',
        )
        self.rol_doctor = Group.objects.create(name='Doctor')
        self.rol_doctor.permissions.add(permiso_view_expediente)
        self.rol_enfermera = Group.objects.create(name='Enfermera')

        self.clinica = Clinica.objects.create(nombre='ProSalud')

        self.doctor = Usuario.objects.create_user(username='doctor', password='clave123')
        self.doctor.groups.add(self.rol_doctor)
        self.doctor.clinicas.add(self.clinica)

        self.enfermera = Usuario.objects.create_user(username='enfermera', password='clave123')
        self.enfermera.groups.add(self.rol_enfermera)

        self.paciente = Persona.objects.create(
            nombres='Diego', apellidos='Guevara Peña', fecha_nacimiento='2015-03-10',
        )
        self.expediente = Expediente.objects.create(persona=self.paciente, clinica=self.clinica)
        self.url = reverse('pacientes:agregar_contacto', args=[self.expediente.id])
        self.url_expediente = reverse('pacientes:ver_expediente', args=[self.expediente.id])

        self.datos_base = {
            'tipo': Contacto.Tipo.RESPONSABLE,
            'persona_id': '',
            'nombres': 'Roberto Antonio',
            'apellidos': 'Guevara Peña',
            'telefono': '7900-3344',
            'parentesco': Contacto.Parentesco.PADRE_MADRE,
            'parentesco_otro': '',
        }

    def test_agregar_contacto_nuevo_crea_persona_y_contacto(self):
        self.client.force_login(self.doctor)
        respuesta = self.client.post(self.url, self.datos_base)

        self.assertRedirects(respuesta, self.url_expediente)
        contacto = Contacto.objects.get(paciente=self.paciente)
        self.assertEqual(contacto.persona_contacto.nombres, 'Roberto Antonio')
        self.assertEqual(contacto.tipo, Contacto.Tipo.RESPONSABLE)

    def test_reutiliza_persona_existente_por_el_buscador(self):
        existente = Persona.objects.create(nombres='Ana', apellidos='Lopez', telefono='7011-9988')
        self.client.force_login(self.doctor)

        datos = dict(self.datos_base, persona_id=existente.pk, nombres='', apellidos='', telefono='')
        respuesta = self.client.post(self.url, datos)

        self.assertRedirects(respuesta, self.url_expediente)
        contacto = Contacto.objects.get(paciente=self.paciente)
        self.assertEqual(contacto.persona_contacto, existente)
        # No se creo una Persona nueva -- se reutilizo la existente.
        self.assertEqual(Persona.objects.filter(nombres='Ana').count(), 1)

    def test_segundo_responsable_no_duplica_la_persona_ni_falla(self):
        """HU-EXP-02: un paciente puede tener mas de un responsable."""
        self.client.force_login(self.doctor)
        self.client.post(self.url, self.datos_base)

        segundo = dict(
            self.datos_base,
            nombres='Marta', apellidos='Peña', telefono='7011-2233',
            parentesco=Contacto.Parentesco.HERMANO,
        )
        respuesta = self.client.post(self.url, segundo)

        self.assertRedirects(respuesta, self.url_expediente)
        self.assertEqual(Contacto.objects.filter(paciente=self.paciente).count(), 2)

    def test_no_puede_ser_su_propio_contacto(self):
        self.client.force_login(self.doctor)
        datos = dict(self.datos_base, persona_id=self.paciente.pk)
        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)  # no redirige: no se guardo
        self.assertContains(respuesta, 'no puede ser su propio contacto')
        self.assertFalse(Contacto.objects.filter(paciente=self.paciente).exists())

    def test_no_puede_agregar_a_la_misma_persona_dos_veces(self):
        existente = Persona.objects.create(nombres='Ana', apellidos='Lopez', telefono='7011-9988')
        Contacto.objects.create(
            paciente=self.paciente, persona_contacto=existente,
            tipo=Contacto.Tipo.RESPONSABLE, parentesco=Contacto.Parentesco.PADRE_MADRE,
        )
        self.client.force_login(self.doctor)

        datos = dict(self.datos_base, persona_id=existente.pk, nombres='', apellidos='', telefono='')
        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'ya es contacto de este paciente')
        self.assertEqual(Contacto.objects.filter(paciente=self.paciente).count(), 1)

    def test_campos_incompletos_no_guarda(self):
        self.client.force_login(self.doctor)
        datos = dict(self.datos_base, telefono='')
        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Completa nombre, apellidos, teléfono y parentesco')
        self.assertFalse(Contacto.objects.filter(paciente=self.paciente).exists())

    def test_duplicado_por_nombre_y_telefono_no_guarda(self):
        Persona.objects.create(nombres='Roberto Antonio', apellidos='Guevara Peña', telefono='7900-3344')
        self.client.force_login(self.doctor)

        respuesta = self.client.post(self.url, self.datos_base)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'búscala arriba en vez de crearla de nuevo')
        self.assertFalse(Contacto.objects.filter(paciente=self.paciente).exists())

    def test_parentesco_otro_requiere_detalle(self):
        self.client.force_login(self.doctor)
        datos = dict(self.datos_base, parentesco=Contacto.Parentesco.OTRO, parentesco_otro='')
        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Especifica cuál es el parentesco')
        self.assertFalse(Contacto.objects.filter(paciente=self.paciente).exists())

    def test_formulario_invalido_reabre_el_modal(self):
        """La pantalla se vuelve a renderizar con la señal para reabrir el modal, no en blanco."""
        self.client.force_login(self.doctor)
        respuesta = self.client.post(self.url, dict(self.datos_base, telefono=''))
        self.assertContains(respuesta, 'data-abrir-modal="true"')

    def test_enfermera_sin_permiso_da_403(self):
        self.client.force_login(self.enfermera)
        respuesta = self.client.post(self.url, self.datos_base)
        self.assertEqual(respuesta.status_code, 403)

    def test_metodo_get_no_permitido(self):
        self.client.force_login(self.doctor)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 405)

    def _crear_expediente_adulto(self):
        adulto = Persona.objects.create(
            nombres='Maria Elena', apellidos='Hernandez Perez', fecha_nacimiento='1988-03-14',
        )
        expediente = Expediente.objects.create(persona=adulto, clinica=self.clinica)
        return adulto, expediente

    def test_adulto_no_ve_el_desplegable_de_tipo(self):
        """HU-EXP-05: 'Responsable' es exclusivo de menores -- un adulto ni ve la eleccion."""
        _, expediente = self._crear_expediente_adulto()
        self.client.force_login(self.doctor)

        respuesta = self.client.get(reverse('pacientes:ver_expediente', args=[expediente.id]))

        self.assertNotContains(respuesta, '<option value="responsable"')
        self.assertContains(respuesta, 'Contacto de referencia')

    def test_menor_si_ve_el_desplegable_de_tipo(self):
        self.client.force_login(self.doctor)
        respuesta = self.client.get(self.url_expediente)
        self.assertContains(respuesta, '<option value="responsable"')

    def test_agregar_contacto_a_adulto_ignora_tipo_manipulado_y_usa_referencia(self):
        """
        Mismo criterio que RegistrarPacienteForm con el interruptor Adulto/
        Menor: no se confia en lo que mande el POST, se decide con la edad
        real del paciente. Un tipo=responsable armado a mano para un adulto
        se guarda igual como REFERENCIA.
        """
        adulto, expediente = self._crear_expediente_adulto()
        url = reverse('pacientes:agregar_contacto', args=[expediente.id])
        self.client.force_login(self.doctor)

        datos = dict(self.datos_base, tipo=Contacto.Tipo.RESPONSABLE)
        respuesta = self.client.post(url, datos)

        self.assertRedirects(respuesta, reverse('pacientes:ver_expediente', args=[expediente.id]))
        contacto = Contacto.objects.get(paciente=adulto)
        self.assertEqual(contacto.tipo, Contacto.Tipo.REFERENCIA)


class EditarYDesactivarContactoTests(PruebaCore):
    """
    Actualizacion de HU-EXP-05 (05/09/2026): editar los datos de un
    contacto ya existente, y "eliminarlo" -- en realidad desactivarlo
    (regla del proyecto: nada se elimina), con la guarda de que un menor
    nunca se quede sin ningun responsable activo.
    """

    def setUp(self):
        permiso_view_expediente = Permission.objects.get(
            content_type__app_label='pacientes', codename='view_expediente',
        )
        self.rol_doctor = Group.objects.create(name='Doctor')
        self.rol_doctor.permissions.add(permiso_view_expediente)
        self.rol_enfermera = Group.objects.create(name='Enfermera')

        self.clinica = Clinica.objects.create(nombre='ProSalud')

        self.doctor = Usuario.objects.create_user(username='doctor', password='clave123')
        self.doctor.groups.add(self.rol_doctor)
        self.doctor.clinicas.add(self.clinica)

        self.enfermera = Usuario.objects.create_user(username='enfermera', password='clave123')
        self.enfermera.groups.add(self.rol_enfermera)

        self.menor = Persona.objects.create(nombres='Diego', apellidos='Guevara Peña', fecha_nacimiento='2015-03-10')
        self.expediente_menor = Expediente.objects.create(persona=self.menor, clinica=self.clinica)

        self.responsable = Persona.objects.create(
            nombres='Roberto Antonio', apellidos='Guevara Peña', telefono='7900-3344',
        )
        self.contacto = Contacto.objects.create(
            paciente=self.menor, persona_contacto=self.responsable,
            tipo=Contacto.Tipo.RESPONSABLE, parentesco=Contacto.Parentesco.PADRE_MADRE,
        )

        self.url_editar = reverse('pacientes:editar_contacto', args=[self.expediente_menor.id, self.contacto.id])
        self.url_desactivar = reverse('pacientes:desactivar_contacto', args=[self.expediente_menor.id, self.contacto.id])
        self.url_expediente = reverse('pacientes:ver_expediente', args=[self.expediente_menor.id])

        self.datos_edicion = {
            'tipo': Contacto.Tipo.RESPONSABLE,
            'nombres': 'Roberto Antonio',
            'apellidos': 'Guevara Peña',
            'telefono': '7900-3344',
            'parentesco': Contacto.Parentesco.PADRE_MADRE,
            'parentesco_otro': '',
        }

    # --- Editar ---

    def test_editar_parentesco_sin_tocar_a_la_persona(self):
        self.client.force_login(self.doctor)
        datos = dict(self.datos_edicion, parentesco=Contacto.Parentesco.ABUELO)

        respuesta = self.client.post(self.url_editar, datos)

        self.assertRedirects(respuesta, self.url_expediente)
        self.contacto.refresh_from_db()
        self.assertEqual(self.contacto.parentesco, Contacto.Parentesco.ABUELO)

    def test_editar_nombre_de_la_persona_se_actualiza_en_la_persona(self):
        """Nombres/apellidos/telefono viven en Persona, no en Contacto -- se edita ahi."""
        self.client.force_login(self.doctor)
        datos = dict(self.datos_edicion, nombres='Roberto', telefono='7900-9999')

        respuesta = self.client.post(self.url_editar, datos)

        self.assertRedirects(respuesta, self.url_expediente)
        self.responsable.refresh_from_db()
        self.assertEqual(self.responsable.nombres, 'Roberto')
        self.assertEqual(self.responsable.telefono, '7900-9999')

    def test_editar_a_adulto_ignora_tipo_manipulado_y_usa_referencia(self):
        adulto = Persona.objects.create(nombres='Maria', apellidos='Perez', fecha_nacimiento='1990-01-01')
        expediente_adulto = Expediente.objects.create(persona=adulto, clinica=self.clinica)
        contacto_adulto = Contacto.objects.create(
            paciente=adulto, persona_contacto=self.responsable,
            tipo=Contacto.Tipo.REFERENCIA, parentesco=Contacto.Parentesco.HERMANO,
        )
        url = reverse('pacientes:editar_contacto', args=[expediente_adulto.id, contacto_adulto.id])
        self.client.force_login(self.doctor)

        respuesta = self.client.post(url, dict(self.datos_edicion, tipo=Contacto.Tipo.RESPONSABLE))

        self.assertRedirects(respuesta, reverse('pacientes:ver_expediente', args=[expediente_adulto.id]))
        contacto_adulto.refresh_from_db()
        self.assertEqual(contacto_adulto.tipo, Contacto.Tipo.REFERENCIA)

    def test_editar_no_puede_duplicar_otra_persona_existente(self):
        Persona.objects.create(nombres='Otra', apellidos='Persona', telefono='7000-0000')
        self.client.force_login(self.doctor)

        datos = dict(self.datos_edicion, nombres='Otra', apellidos='Persona', telefono='7000-0000')
        respuesta = self.client.post(self.url_editar, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Ya existe otra persona registrada')
        self.responsable.refresh_from_db()
        self.assertEqual(self.responsable.nombres, 'Roberto Antonio')  # no se modifico

    def test_editar_no_falla_al_no_cambiar_nombre_ni_telefono(self):
        """Guardar sin tocar nombre/telefono (solo el parentesco) no debe chocar con la propia Persona."""
        self.client.force_login(self.doctor)
        respuesta = self.client.post(self.url_editar, self.datos_edicion)
        self.assertRedirects(respuesta, self.url_expediente)

    def test_parentesco_otro_requiere_detalle_al_editar(self):
        self.client.force_login(self.doctor)
        datos = dict(self.datos_edicion, parentesco=Contacto.Parentesco.OTRO, parentesco_otro='')
        respuesta = self.client.post(self.url_editar, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Especifica cuál es el parentesco')

    def test_editar_enfermera_sin_permiso_da_403(self):
        self.client.force_login(self.enfermera)
        respuesta = self.client.post(self.url_editar, self.datos_edicion)
        self.assertEqual(respuesta.status_code, 403)

    def test_editar_get_no_permitido(self):
        self.client.force_login(self.doctor)
        respuesta = self.client.get(self.url_editar)
        self.assertEqual(respuesta.status_code, 405)

    def test_no_se_puede_editar_contacto_de_otro_expediente(self):
        """IDOR: el contacto pertenece a otro paciente -- 404, no se permite editarlo desde aqui."""
        otro_paciente = Persona.objects.create(nombres='Otro', apellidos='Paciente', fecha_nacimiento='1985-01-01')
        otro_expediente = Expediente.objects.create(persona=otro_paciente, clinica=self.clinica)
        url = reverse('pacientes:editar_contacto', args=[otro_expediente.id, self.contacto.id])
        self.client.force_login(self.doctor)

        respuesta = self.client.post(url, self.datos_edicion)

        self.assertEqual(respuesta.status_code, 404)

    # --- Desactivar ---

    def test_desactivar_contacto_de_referencia_de_un_adulto(self):
        adulto = Persona.objects.create(nombres='Maria', apellidos='Perez', fecha_nacimiento='1990-01-01')
        expediente_adulto = Expediente.objects.create(persona=adulto, clinica=self.clinica)
        contacto_adulto = Contacto.objects.create(
            paciente=adulto, persona_contacto=self.responsable,
            tipo=Contacto.Tipo.REFERENCIA, parentesco=Contacto.Parentesco.HERMANO,
        )
        url = reverse('pacientes:desactivar_contacto', args=[expediente_adulto.id, contacto_adulto.id])
        self.client.force_login(self.doctor)

        respuesta = self.client.post(url)

        self.assertRedirects(respuesta, reverse('pacientes:ver_expediente', args=[expediente_adulto.id]))
        contacto_adulto.refresh_from_db()
        self.assertFalse(contacto_adulto.activo)

    def test_no_se_puede_desactivar_el_unico_responsable_de_un_menor(self):
        self.client.force_login(self.doctor)

        respuesta = self.client.post(self.url_desactivar)

        # No se usa assertRedirects: internamente sigue la redirección para
        # verificarla, y esa segunda petición consume el mensaje flash antes
        # de que el GET explícito de abajo pueda leerlo.
        self.assertRedirects(respuesta, self.url_expediente, fetch_redirect_response=False)
        self.contacto.refresh_from_db()
        self.assertTrue(self.contacto.activo)  # sigue activo, no se desactivo
        respuesta_pagina = self.client.get(self.url_expediente)
        self.assertContains(respuesta_pagina, 'es el único responsable')

    def test_si_se_puede_desactivar_un_responsable_si_queda_otro(self):
        segundo_responsable = Persona.objects.create(nombres='Ana', apellidos='Lopez', telefono='7011-9988')
        segundo_contacto = Contacto.objects.create(
            paciente=self.menor, persona_contacto=segundo_responsable,
            tipo=Contacto.Tipo.RESPONSABLE, parentesco=Contacto.Parentesco.PADRE_MADRE,
        )
        self.client.force_login(self.doctor)

        respuesta = self.client.post(self.url_desactivar)

        self.assertRedirects(respuesta, self.url_expediente)
        self.contacto.refresh_from_db()
        self.assertFalse(self.contacto.activo)
        segundo_contacto.refresh_from_db()
        self.assertTrue(segundo_contacto.activo)

    def test_desactivado_ya_no_aparece_en_la_lista_de_contactos(self):
        segundo_responsable = Persona.objects.create(nombres='Ana', apellidos='Lopez', telefono='7011-9988')
        Contacto.objects.create(
            paciente=self.menor, persona_contacto=segundo_responsable,
            tipo=Contacto.Tipo.RESPONSABLE, parentesco=Contacto.Parentesco.PADRE_MADRE,
        )
        self.client.force_login(self.doctor)
        self.client.post(self.url_desactivar)

        respuesta = self.client.get(self.url_expediente)

        # No se compara el nombre completo: el propio mensaje de éxito
        # ("Roberto Antonio ... ya no es contacto") lo menciona a propósito.
        # Lo que debe desaparecer es la FILA de la lista -- se verifica por
        # el atributo del botón "Editar", que solo existe para contactos activos.
        self.assertNotContains(respuesta, 'data-nombres="Roberto Antonio"')

    def test_desactivar_enfermera_sin_permiso_da_403(self):
        self.client.force_login(self.enfermera)
        respuesta = self.client.post(self.url_desactivar)
        self.assertEqual(respuesta.status_code, 403)

    def test_desactivar_get_no_permitido(self):
        self.client.force_login(self.doctor)
        respuesta = self.client.get(self.url_desactivar)
        self.assertEqual(respuesta.status_code, 405)

    def test_no_se_puede_desactivar_contacto_de_otro_expediente(self):
        otro_paciente = Persona.objects.create(nombres='Otro', apellidos='Paciente', fecha_nacimiento='1985-01-01')
        otro_expediente = Expediente.objects.create(persona=otro_paciente, clinica=self.clinica)
        url = reverse('pacientes:desactivar_contacto', args=[otro_expediente.id, self.contacto.id])
        self.client.force_login(self.doctor)

        respuesta = self.client.post(url)

        self.assertEqual(respuesta.status_code, 404)


class RegistrarPreconsultaTests(PruebaCore):
    """Signos vitales, calculo de IMC y asignacion de medico en una sola pantalla."""

    def setUp(self):
        self.rol_enfermera = Group.objects.create(name='Enfermera')
        self.rol_enfermera.permissions.add(
            Permission.objects.get(content_type__app_label='pacientes', codename='view_persona'),
            Permission.objects.get(content_type__app_label='consultas', codename='add_signosvitales'),
            Permission.objects.get(content_type__app_label='consultas', codename='add_consulta'),
        )
        self.rol_doctor = Group.objects.create(name='Doctor')
        self.rol_doctor.permissions.add(
            Permission.objects.get(content_type__app_label='consultas', codename='change_consulta'),
            Permission.objects.get(content_type__app_label='pacientes', codename='view_persona'),
        )

        self.clinica = Clinica.objects.create(nombre='ProSalud')
        self.otra_clinica = Clinica.objects.create(nombre='Estética')

        self.enfermera = Usuario.objects.create_user(username='enfermera', password='x')
        self.enfermera.groups.add(self.rol_enfermera)
        self.enfermera.clinicas.add(self.clinica)

        self.medico = Usuario.objects.create_user(
            username='doctor1', password='x', first_name='Ana', last_name='Médica',
        )
        self.medico.groups.add(self.rol_doctor)
        self.medico.clinicas.add(self.clinica)

        self.paciente = Persona.objects.create(
            nombres='Roberto Antonio', apellidos='Guevara Peña', fecha_nacimiento='1993-06-15',
        )
        self.expediente = Expediente.objects.create(persona=self.paciente, clinica=self.clinica)
        self.url = reverse('pacientes:registrar_preconsulta', args=[self.expediente.id])

        self.datos_base = {'peso': '70.5', 'medico': str(self.medico.pk)}

    def test_enfermera_registra_preconsulta_de_un_adulto(self):
        self.client.force_login(self.enfermera)
        datos = dict(self.datos_base, presion_arterial='120/80')

        respuesta = self.client.post(self.url, datos)

        self.assertRedirects(respuesta, reverse('pacientes:lista_pacientes'))
        consulta = Consulta.objects.get(expediente=self.expediente)
        self.assertEqual(consulta.doctor, self.medico)
        self.assertIsNone(consulta.inicio)  # en_cola: sin iniciar todavia
        self.assertTrue(consulta.en_cola)
        signos = SignosVitales.objects.get(consulta=consulta)
        self.assertEqual(str(signos.peso), '70.50')
        self.assertEqual(signos.presion_arterial, '120/80')
        self.assertEqual(signos.tomado_por, self.enfermera)

    def test_peso_es_obligatorio(self):
        self.client.force_login(self.enfermera)
        datos = dict(self.datos_base)
        del datos['peso']

        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Consulta.objects.filter(expediente=self.expediente).exists())

    def test_sin_peso_pero_con_talla_no_truena(self):
        """Antes tronaba con TypeError al calcular el IMC sin peso."""
        self.client.force_login(self.enfermera)
        datos = dict(self.datos_base, talla='1.20')
        del datos['peso']

        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Consulta.objects.filter(expediente=self.expediente).exists())

    def test_sin_medico_no_crea_consulta_ni_signos_vitales(self):
        """La consulta nunca se crea sin medico."""
        self.client.force_login(self.enfermera)
        datos = dict(self.datos_base)
        del datos['medico']

        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Consulta.objects.filter(expediente=self.expediente).exists())
        self.assertFalse(SignosVitales.objects.exists())

    def test_calcula_imc_automaticamente_con_peso_y_talla(self):
        self.client.force_login(self.enfermera)
        datos = dict(self.datos_base, talla='1.70')

        self.client.post(self.url, datos)

        signos = SignosVitales.objects.get(consulta__expediente=self.expediente)
        self.assertEqual(str(signos.imc), '24.4')  # 70.5 / 1.70**2 = 24.39...

    def test_sin_talla_el_imc_queda_vacio_sin_error(self):
        self.client.force_login(self.enfermera)

        respuesta = self.client.post(self.url, self.datos_base)

        self.assertRedirects(respuesta, reverse('pacientes:lista_pacientes'))
        signos = SignosVitales.objects.get(consulta__expediente=self.expediente)
        self.assertIsNone(signos.imc)

    def test_no_permite_dos_consultas_abiertas_del_mismo_paciente(self):
        Consulta.objects.create(expediente=self.expediente, doctor=self.medico, motivo='')
        self.client.force_login(self.enfermera)

        respuesta = self.client.post(self.url, self.datos_base)

        self.assertRedirects(respuesta, reverse('pacientes:lista_pacientes'))
        self.assertEqual(Consulta.objects.filter(expediente=self.expediente).count(), 1)  # no se creo una segunda

    def test_medicos_disponibles_muestra_cuantos_tiene_en_cola(self):
        Consulta.objects.create(expediente=self.expediente, doctor=self.medico, motivo='')
        otro_paciente = Persona.objects.create(nombres='Ana', apellidos='Lopez', fecha_nacimiento='1990-01-01')
        otro_expediente = Expediente.objects.create(persona=otro_paciente, clinica=self.clinica)
        self.client.force_login(self.enfermera)

        respuesta = self.client.get(reverse('pacientes:registrar_preconsulta', args=[otro_expediente.id]))

        medicos = {m.pk: m for m in respuesta.context['medicos']}
        self.assertEqual(medicos[self.medico.pk].pacientes_en_cola, 1)

    def test_medico_de_otra_clinica_no_es_valido(self):
        """El medico se valida contra el queryset de ESTA clinica -- no basta con mandar cualquier id."""
        medico_ajeno = Usuario.objects.create_user(username='doctor2', password='x')
        medico_ajeno.groups.add(self.rol_doctor)
        medico_ajeno.clinicas.add(self.otra_clinica)
        self.client.force_login(self.enfermera)

        datos = dict(self.datos_base, medico=str(medico_ajeno.pk))
        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Consulta.objects.filter(expediente=self.expediente).exists())

    def test_doctor_sin_permiso_de_preconsulta_da_403(self):
        self.client.force_login(self.medico)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 403)

    def test_enfermera_de_otra_clinica_da_403(self):
        self.enfermera.clinicas.set([self.otra_clinica])
        self.client.force_login(self.enfermera)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 403)

    def test_boton_enviar_a_consulta_visible_solo_para_enfermera(self):
        url_lista = reverse('pacientes:lista_pacientes')

        self.client.force_login(self.enfermera)
        respuesta_enfermera = self.client.get(url_lista)
        self.assertContains(respuesta_enfermera, 'Enviar a consulta')

        self.client.force_login(self.medico)
        respuesta_medico = self.client.get(url_lista)
        self.assertNotContains(respuesta_medico, 'Enviar a consulta')

    def test_presion_arterial_incompleta_no_es_valida(self):
        """'120/8' -- le falto un digito a la diastolica, no se acepta a medias."""
        self.client.force_login(self.enfermera)
        datos = dict(self.datos_base, presion_arterial='120/8')

        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Consulta.objects.filter(expediente=self.expediente).exists())
        self.assertContains(respuesta, 'Formato inválido')

    def test_presion_sistolica_fuera_de_rango_no_es_valida(self):
        self.client.force_login(self.enfermera)
        datos = dict(self.datos_base, presion_arterial='300/80')

        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Consulta.objects.filter(expediente=self.expediente).exists())
        self.assertContains(respuesta, 'sistólica')

    def test_presion_diastolica_fuera_de_rango_no_es_valida(self):
        self.client.force_login(self.enfermera)
        datos = dict(self.datos_base, presion_arterial='120/10')

        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Consulta.objects.filter(expediente=self.expediente).exists())
        self.assertContains(respuesta, 'diastólica')

    def test_presion_arterial_valida_en_los_bordes_del_rango_se_guarda(self):
        self.client.force_login(self.enfermera)
        datos = dict(self.datos_base, presion_arterial='60/30')

        respuesta = self.client.post(self.url, datos)

        self.assertRedirects(respuesta, reverse('pacientes:lista_pacientes'))
        signos = SignosVitales.objects.get(consulta__expediente=self.expediente)
        self.assertEqual(signos.presion_arterial, '60/30')

    def test_talla_fuera_de_rango_no_se_guarda(self):
        self.client.force_login(self.enfermera)
        datos = dict(self.datos_base, talla='5.00')

        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Consulta.objects.filter(expediente=self.expediente).exists())

    def test_talla_valida_en_los_bordes_del_rango_se_guarda(self):
        self.client.force_login(self.enfermera)
        datos = dict(self.datos_base, talla='2.20')

        respuesta = self.client.post(self.url, datos)

        self.assertRedirects(respuesta, reverse('pacientes:lista_pacientes'))
        signos = SignosVitales.objects.get(consulta__expediente=self.expediente)
        self.assertEqual(str(signos.talla), '2.20')

    def test_temperatura_fuera_de_rango_no_se_guarda(self):
        self.client.force_login(self.enfermera)
        datos = dict(self.datos_base, temperatura='50.0')

        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Consulta.objects.filter(expediente=self.expediente).exists())

    def test_frecuencia_cardiaca_fuera_de_rango_no_se_guarda(self):
        self.client.force_login(self.enfermera)
        datos = dict(self.datos_base, frecuencia_cardiaca='300')

        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Consulta.objects.filter(expediente=self.expediente).exists())

    def test_saturacion_fuera_de_rango_no_se_guarda(self):
        self.client.force_login(self.enfermera)
        datos = dict(self.datos_base, saturacion='150')

        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Consulta.objects.filter(expediente=self.expediente).exists())

    def test_temperatura_frecuencia_saturacion_validas_se_guardan(self):
        self.client.force_login(self.enfermera)
        datos = dict(self.datos_base, temperatura='38.5', frecuencia_cardiaca='90', saturacion='97')

        respuesta = self.client.post(self.url, datos)

        self.assertRedirects(respuesta, reverse('pacientes:lista_pacientes'))
        signos = SignosVitales.objects.get(consulta__expediente=self.expediente)
        self.assertEqual(str(signos.temperatura), '38.5')
        self.assertEqual(signos.frecuencia_cardiaca, 90)
        self.assertEqual(signos.saturacion, 97)
