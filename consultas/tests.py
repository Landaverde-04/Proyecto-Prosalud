from datetime import date, timedelta
from unittest.mock import patch
from reportlab.platypus import Paragraph
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone
from core.models import Clinica
from core.tests import PruebaCore
from pacientes.models import Persona, Expediente
from seguridad.models import Usuario
from .forms import ConsultaClinicaForm, DocumentoMedicoForm
from .models import Antecedente, Consulta, Incapacidad
from .documentos import generar_pdf, anio_en_letras


class DocumentosMedicosTests(PruebaCore):
    def setUp(self):
        self.doctor = Usuario.objects.create_user(username='medico', password='prueba', first_name='Ana', last_name='Médica', debe_cambiar_password=False)
        self.doctor.user_permissions.add(*Permission.objects.filter(codename__in=['view_expediente', 'view_incapacidad', 'add_incapacidad']))
        self.clinica = Clinica.objects.create(nombre='ProSalud')
        self.doctor.clinicas.add(self.clinica)
        self.persona = Persona.objects.create(nombres='Paciente', apellidos='Ficticio')
        self.expediente = Expediente.objects.create(persona=self.persona, clinica=self.clinica)
        self.consulta = Consulta.objects.create(expediente=self.expediente, doctor=self.doctor, doctor_nombre='Ana Médica', motivo='Atención de prueba', diagnostico='Diagnóstico de prueba')
        self.client.force_login(self.doctor)
        self.url = reverse('consultas:nuevo_documento', args=[self.consulta.pk])
        self.datos = {'tipo':'incapacidad','motivo':'Motivo revisado','dias':'5','inicio_opcion':'personalizada','fecha_inicio_incapacidad':'2026-09-05'}

    def previa(self, datos=None):
        r=self.client.post(self.url, datos or self.datos)
        self.assertEqual(r.status_code,302)
        return r.url.split('/')[-2]

    def emitir(self, previa):
        return self.client.post(reverse('consultas:emitir_documento',args=[previa]))

    def test_previa_no_guarda_ni_cierra_consulta(self):
        previa=self.previa()
        r=self.client.get(reverse('consultas:pdf_previa',args=[previa]))
        self.assertEqual(r.status_code,200);self.assertTrue(r.content.startswith(b'%PDF'))
        self.assertEqual(r['X-Frame-Options'],'SAMEORIGIN')
        self.assertIn('no-store',r['Cache-Control'])
        self.assertFalse(Incapacidad.objects.exists())
        self.consulta.refresh_from_db();self.assertIsNone(self.consulta.cierre)

    def test_emision_repetida_y_datos_relacionados(self):
        previa=self.previa();primera=self.emitir(previa);segunda=self.emitir(previa)
        self.assertEqual(primera.url,segunda.url);self.assertEqual(Incapacidad.objects.count(),1)
        doc=Incapacidad.objects.get();self.assertEqual(doc.fecha_fin,date(2026,9,9))
        self.assertEqual(doc.consulta_id,self.consulta.pk);self.assertEqual(doc.creado_por,self.doctor)
        self.persona.nombres='Nombre cambiado';self.persona.save()
        self.doctor.first_name='Otra';self.doctor.save()
        doc=Incapacidad.objects.get(pk=doc.pk)
        self.assertEqual(str(doc.consulta.expediente.persona),'Nombre cambiado Ficticio')
        # El documento congela al medico: corregir el perfil no lo reescribe.
        self.assertEqual(doc.doctor_nombre,'Ana Médica')
        self.assertEqual(doc.nombre_profesional,'Ana Médica')
        r=self.client.get(reverse('consultas:pdf_documento',args=[doc.pk])+'?descargar=1')
        self.assertEqual(r.status_code,200);self.assertIn('attachment',r['Content-Disposition'])
        self.consulta.refresh_from_db();self.assertIsNone(self.consulta.cierre)

    def test_un_solo_formato_y_dias_obligatorios(self):
        self.assertFalse(DocumentoMedicoForm({'tipo':'constancia','motivo':'Prueba'}).is_valid())
        form=DocumentoMedicoForm({**self.datos,'tipo':'constancia'})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['tipo'],'incapacidad')
        self.assertNotContains(self.client.get(self.url),'id_tipo')

    def test_periodos_inclusivos(self):
        for inicio,dias,fin in [(date(2026,9,5),1,date(2026,9,5)),(date(2026,12,30),5,date(2027,1,3)),(date(2028,2,28),3,date(2028,3,1))]:
            with self.subTest(inicio=inicio):
                doc=Incapacidad(tipo='incapacidad',fecha_inicio_incapacidad=inicio,dias=dias)
                self.assertEqual(doc.fecha_fin,fin)

    def test_hoy_se_calcula_en_servidor(self):
        datos={**self.datos,'inicio_opcion':'hoy','fecha_inicio_incapacidad':'2000-01-01'}
        form=DocumentoMedicoForm(datos);self.assertTrue(form.is_valid());self.assertEqual(form.cleaned_data['fecha_inicio_incapacidad'],timezone.localdate())

    def test_validaciones(self):
        for cambio in [{'dias':'0'},{'dias':'-1'},{'dias':'1.5'},{'dias':''},{'fecha_inicio_incapacidad':''},{'motivo':'  '},{'dias':'999999999999'}]:
            with self.subTest(cambio=cambio):self.assertFalse(DocumentoMedicoForm({**self.datos,**cambio}).is_valid())

    def test_sin_permiso_y_otra_clinica(self):
        self.doctor.clinicas.clear();self.assertEqual(self.client.get(self.url).status_code,403)
        self.doctor.clinicas.add(self.clinica);self.doctor.user_permissions.clear()
        self.assertEqual(self.client.get(self.url).status_code,403)

    def test_documento_no_se_puede_leer_fuera_de_clinica(self):
        self.emitir(self.previa());doc=Incapacidad.objects.get();self.doctor.clinicas.clear()
        for nombre in ['ver_documento','pdf_documento']:
            self.assertEqual(self.client.get(reverse('consultas:'+nombre,args=[doc.pk])).status_code,403)

    def test_previa_de_otra_sesion_no_es_accesible(self):
        previa=self.previa();self.client.logout();self.client.force_login(self.doctor)
        self.assertEqual(self.client.get(reverse('consultas:pdf_previa',args=[previa])).status_code,404)

    def test_previa_vencida_no_emite(self):
        previa=self.previa()
        with patch('consultas.views.time.time',return_value=timezone.now().timestamp()+1900):
            self.assertEqual(self.emitir(previa).status_code,404)
        self.assertFalse(Incapacidad.objects.exists())

    def test_get_no_emite(self):
        previa=self.previa();self.assertEqual(self.client.get(reverse('consultas:emitir_documento',args=[previa])).status_code,405)
        self.assertFalse(Incapacidad.objects.exists())

    def test_formulario_listado_y_previa_renderizan(self):
        self.assertContains(self.client.get(self.url),'Previsualizar documento')
        previa=self.previa()
        self.assertContains(self.client.get(reverse('consultas:previsualizar_documento',args=[previa])),'Emitir y guardar')
        self.assertEqual(self.client.get(reverse('consultas:lista_documentos',args=[self.expediente.pk])).status_code,200)

    def test_motivo_largo_y_caracteres_especiales_en_pdf(self):
        previa=self.previa({**self.datos,'motivo':('Prueba <etiqueta> & acentos áéíóú. '*120)})
        r=self.client.get(reverse('consultas:pdf_previa',args=[previa]));self.assertEqual(r.status_code,200)

    def test_pdf_toma_paciente_de_la_relacion_y_congela_al_medico(self):
        self.doctor.jvpm = '15856'
        self.doctor.save()
        self.emitir(self.previa())
        self.persona.nombres = 'Paciente actualizado'
        self.persona.save()
        self.doctor.first_name = 'Doctora actualizada'
        self.doctor.jvpm = '98765'
        self.doctor.save()
        doc = Incapacidad.objects.select_related(
            'consulta__doctor', 'consulta__expediente__persona', 'consulta__expediente__clinica',
        ).get()
        with patch('consultas.documentos.Paragraph', wraps=Paragraph) as parrafo:
            pdf = generar_pdf(doc)
        texto = ' '.join(call.args[0] for call in parrafo.call_args_list)
        self.assertTrue(pdf.startswith(b'%PDF'))
        # El paciente se lee de su expediente: no se guarda una copia del nombre.
        self.assertIn('Paciente actualizado Ficticio', texto)
        # El nombre del medico queda como firmo: puede cambiar, asi que se congela.
        self.assertIn('Ana Médica', texto)
        self.assertNotIn('Doctora actualizada', texto)
        # El JVPM se lee del perfil: es un identificador permanente, no se copia.
        self.assertIn('J.V.P.M. 98765', texto)
        self.assertIn('7629-2725', texto)

    def test_previa_anterior_a_correccion_pide_revisar(self):
        previa = self.previa()
        sesion = self.client.session
        previas = sesion['documentos_previas']
        campos = previas[previa]['campos']
        campos['fecha_inicio'] = campos.pop('fecha_inicio_incapacidad')
        campos['paciente_nombre'] = 'Copia anterior'
        sesion['documentos_previas'] = previas
        sesion.save()
        self.assertEqual(self.emitir(previa).status_code, 404)
        self.assertFalse(Incapacidad.objects.exists())

    def test_emisor_es_medico_de_sesion_y_reimpresion_lo_conserva(self):
        self.doctor.jvpm = '11111'
        self.doctor.save()
        emisor = Usuario.objects.create_user(
            username='segundo_medico', password='prueba', first_name='Luis',
            last_name='Emisor', jvpm='22222', debe_cambiar_password=False,
        )
        emisor.clinicas.add(self.clinica)
        emisor.user_permissions.add(*Permission.objects.filter(
            codename__in=['view_expediente', 'view_incapacidad', 'add_incapacidad'],
        ))
        self.client.force_login(emisor)
        self.assertContains(self.client.get(self.url), 'Luis Emisor')
        previa = self.previa()
        with patch('consultas.documentos.Paragraph', wraps=Paragraph) as parrafo:
            respuesta = self.client.get(reverse('consultas:pdf_previa', args=[previa]))
        self.assertEqual(respuesta.status_code, 200)
        texto = ' '.join(call.args[0] for call in parrafo.call_args_list)
        self.assertIn('Luis Emisor', texto)
        self.assertIn('J.V.P.M. 22222', texto)
        self.assertNotIn('Ana Médica', texto)
        self.assertFalse(Incapacidad.objects.exists())
        self.emitir(previa)
        doc = Incapacidad.objects.get()
        self.assertEqual(doc.creado_por_id, emisor.pk)
        self.assertEqual(doc.consulta.doctor_id, self.doctor.pk)
        self.assertEqual(doc.nombre_profesional, 'Luis Emisor')
        # Otra sesión puede consultar, pero no sustituye al emisor del documento.
        self.client.force_login(self.doctor)
        with patch('consultas.documentos.Paragraph', wraps=Paragraph) as parrafo:
            respuesta = self.client.get(reverse('consultas:pdf_documento', args=[doc.pk]))
        self.assertEqual(respuesta.status_code, 200)
        texto = ' '.join(call.args[0] for call in parrafo.call_args_list)
        self.assertIn('Luis Emisor', texto)
        self.assertIn('J.V.P.M. 22222', texto)
        self.assertNotIn('J.V.P.M. 11111', texto)
        self.assertContains(self.client.get(reverse('consultas:lista_documentos', args=[self.expediente.pk])), 'Luis Emisor')

    def test_documento_anterior_sin_creador_usa_medico_consulta(self):
        self.doctor.jvpm = '15856'
        self.doctor.save()
        doc = Incapacidad(consulta=self.consulta)
        self.assertEqual(doc.profesional_emisor, self.doctor)
        self.assertEqual(doc.nombre_profesional, 'Ana Médica')
        self.assertEqual(doc.jvpm_profesional, '15856')


class AnioDocumentoTests(PruebaCore):
    def test_anio_de_emision_en_letras(self):
        for anio, esperado in [(2026, 'dos mil veintiséis'), (2027, 'dos mil veintisiete'),
                               (2030, 'dos mil treinta'), (2031, 'dos mil treinta y uno'),
                               (2100, 'dos mil cien'), (2000, 'dos mil'),
                               (1999, 'mil novecientos noventa y nueve')]:
            with self.subTest(anio=anio):
                self.assertEqual(anio_en_letras(anio), esperado)


class ConsultaTests(PruebaCore):
    """HU-EXP-17/18/19: registrar, atender, preguardar, finalizar y consultar."""

    def setUp(self):
        self.doctor = Usuario.objects.create_user(
            username='medica', password='prueba', first_name='Ana', last_name='Médica',
            debe_cambiar_password=False)
        self.doctor.user_permissions.add(*Permission.objects.filter(
            codename__in=['view_expediente', 'add_consulta', 'change_consulta', 'view_consulta']))
        self.clinica = Clinica.objects.create(nombre='ProSalud')
        self.doctor.clinicas.add(self.clinica)
        self.persona = Persona.objects.create(nombres='Paciente', apellidos='Ficticio')
        self.expediente = Expediente.objects.create(persona=self.persona, clinica=self.clinica)
        self.client.force_login(self.doctor)
        self.url_nueva = reverse('consultas:nueva_consulta', args=[self.expediente.pk])

    def crear(self, fecha='2026-09-04', hora='09:30'):
        respuesta = self.client.post(self.url_nueva, {'fecha': fecha, 'hora': hora})
        self.assertEqual(respuesta.status_code, 302)
        return Consulta.objects.get()

    def test_registro_manual_usa_la_fecha_y_hora_dictadas(self):
        consulta = self.crear()
        inicio = timezone.localtime(consulta.inicio)
        self.assertEqual(inicio.date(), date(2026, 9, 4))
        self.assertEqual((inicio.hour, inicio.minute), (9, 30))
        # Nace abierta: se llena mientras se atiende, no antes.
        self.assertTrue(consulta.en_atencion)
        self.assertIsNone(consulta.cierre)
        self.assertEqual(consulta.doctor, self.doctor)
        self.assertEqual(consulta.doctor_nombre, 'Ana Médica')
        self.assertEqual(consulta.creado_por, self.doctor)

    def test_no_permite_registrar_una_atencion_en_el_futuro(self):
        manana = timezone.localdate() + timedelta(days=1)
        respuesta = self.client.post(self.url_nueva, {'fecha': manana.isoformat(), 'hora': '09:00'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Consulta.objects.exists())

    def test_no_abre_una_segunda_consulta_si_ya_hay_una_sin_finalizar(self):
        consulta = self.crear()
        respuesta = self.client.post(self.url_nueva, {'fecha': '2026-09-05', 'hora': '10:00'})
        self.assertRedirects(respuesta, reverse('consultas:atender_consulta', args=[consulta.pk]))
        self.assertEqual(Consulta.objects.count(), 1)

    def test_consulta_en_cola_no_inicia_sola_hasta_pulsar_iniciar(self):
        # Asi nacera la consulta cuando exista la preconsulta de Kevin.
        consulta = Consulta.objects.create(expediente=self.expediente, doctor=self.doctor, motivo='')
        self.assertTrue(consulta.en_cola)
        self.assertContains(self.client.get(reverse('consultas:atender_consulta', args=[consulta.pk])),
                            'Iniciar consulta')
        self.client.post(reverse('consultas:iniciar_consulta', args=[consulta.pk]))
        consulta.refresh_from_db()
        self.assertIsNotNone(consulta.inicio)
        self.assertTrue(consulta.en_atencion)

    def test_preguardado_conserva_lo_escrito_sin_exigir_campos(self):
        consulta = self.crear()
        url = reverse('consultas:guardar_borrador', args=[consulta.pk])
        # Sin motivo todavia: exigirlo aqui perderia lo que ya lleva escrito.
        respuesta = self.client.post(url, {'motivo': '', 'examen_fisico': 'Paciente estable'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.json()['ok'])
        consulta.refresh_from_db()
        self.assertEqual(consulta.examen_fisico, 'Paciente estable')
        self.assertEqual(consulta.modificado_por, self.doctor)
        self.assertIsNone(consulta.cierre)

    def test_no_se_preguarda_sobre_una_consulta_finalizada(self):
        consulta = self.crear()
        self.client.post(reverse('consultas:guardar_borrador', args=[consulta.pk]), {'motivo': 'Dolor'})
        self.client.post(reverse('consultas:finalizar_consulta', args=[consulta.pk]))
        respuesta = self.client.post(reverse('consultas:guardar_borrador', args=[consulta.pk]),
                                     {'motivo': 'Cambiado'})
        self.assertEqual(respuesta.status_code, 409)
        consulta.refresh_from_db()
        self.assertEqual(consulta.motivo, 'Dolor')

    def test_no_finaliza_sin_motivo(self):
        consulta = self.crear()
        respuesta = self.client.post(reverse('consultas:finalizar_consulta', args=[consulta.pk]))
        self.assertRedirects(respuesta, reverse('consultas:atender_consulta', args=[consulta.pk]))
        consulta.refresh_from_db()
        self.assertIsNone(consulta.cierre)

    def test_finalizar_cierra_y_deja_la_consulta_de_solo_lectura(self):
        consulta = self.crear()
        self.client.post(reverse('consultas:guardar_borrador', args=[consulta.pk]),
                         {'motivo': 'Dolor de cabeza', 'diagnostico': 'Cefalea'})
        respuesta = self.client.post(reverse('consultas:finalizar_consulta', args=[consulta.pk]))
        self.assertRedirects(respuesta, reverse('consultas:ver_consulta', args=[consulta.pk]))
        consulta.refresh_from_db()
        self.assertTrue(consulta.cerrada)
        # Entrar a atenderla lleva al detalle: cerrada ya no se edita.
        self.assertRedirects(self.client.get(reverse('consultas:atender_consulta', args=[consulta.pk])),
                             reverse('consultas:ver_consulta', args=[consulta.pk]))

    def test_finalizar_no_depende_de_emitir_receta(self):
        consulta = self.crear()
        self.client.post(reverse('consultas:guardar_borrador', args=[consulta.pk]), {'motivo': 'Control'})
        self.client.post(reverse('consultas:finalizar_consulta', args=[consulta.pk]))
        consulta.refresh_from_db()
        self.assertTrue(consulta.cerrada)
        self.assertFalse(hasattr(consulta, 'receta'))

    def test_historial_ordena_de_la_mas_reciente_y_busca(self):
        vieja = Consulta.objects.create(
            expediente=self.expediente, doctor=self.doctor, motivo='Dolor de garganta',
            diagnostico='Faringitis', inicio=timezone.now() - timedelta(days=30),
            cierre=timezone.now() - timedelta(days=30))
        reciente = Consulta.objects.create(
            expediente=self.expediente, doctor=self.doctor, motivo='Fiebre',
            diagnostico='Resfriado', inicio=timezone.now(), cierre=timezone.now())
        url = reverse('consultas:historial_consultas', args=[self.expediente.pk])
        pagina = self.client.get(url).context['pagina'].object_list
        self.assertEqual([c.pk for c in pagina], [reciente.pk, vieja.pk])
        # Busca sin importar tildes ni mayusculas, como el resto del sistema.
        encontradas = self.client.get(url, {'q': 'faringitis'}).context['pagina'].object_list
        self.assertEqual([c.pk for c in encontradas], [vieja.pk])

    def test_historial_responde_solo_el_fragmento_a_listado_vivo(self):
        self.crear()
        respuesta = self.client.get(reverse('consultas:historial_consultas', args=[self.expediente.pk]),
                                    HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertTemplateUsed(respuesta, 'consultas/resultados_consultas.html')
        self.assertTemplateNotUsed(respuesta, 'consultas/historial_consultas.html')

    def test_consulta_en_espera_no_desplaza_a_las_atendidas(self):
        atendida = Consulta.objects.create(expediente=self.expediente, doctor=self.doctor,
                                           motivo='Atendida', inicio=timezone.now(), cierre=timezone.now())
        en_cola = Consulta.objects.create(expediente=self.expediente, doctor=self.doctor, motivo='En cola')
        pagina = self.client.get(reverse('consultas:historial_consultas',
                                        args=[self.expediente.pk])).context['pagina'].object_list
        self.assertEqual([c.pk for c in pagina], [atendida.pk, en_cola.pk])

    def test_detalle_muestra_los_campos_clinicos_y_sus_documentos(self):
        consulta = self.crear()
        self.client.post(reverse('consultas:guardar_borrador', args=[consulta.pk]),
                         {'motivo': 'Dolor abdominal', 'indicaciones': 'Reposo relativo'})
        respuesta = self.client.get(reverse('consultas:ver_consulta', args=[consulta.pk]))
        self.assertContains(respuesta, 'Dolor abdominal')
        self.assertContains(respuesta, 'Reposo relativo')
        self.assertContains(respuesta, 'Motivo de consulta')
        self.assertContains(respuesta, 'No se ha emitido ningún documento')

    def test_documentos_se_emiten_durante_la_atencion(self):
        # Es cuando la doctora tiene al paciente enfrente, no despues de cerrar.
        self.doctor.user_permissions.add(*Permission.objects.filter(
            codename__in=['add_incapacidad', 'view_incapacidad']))
        self.doctor = Usuario.objects.get(pk=self.doctor.pk)
        self.client.force_login(self.doctor)
        consulta = self.crear()
        respuesta = self.client.get(reverse('consultas:atender_consulta', args=[consulta.pk]))
        self.assertContains(respuesta, reverse('consultas:nuevo_documento', args=[consulta.pk]))
        self.assertContains(respuesta, 'Emitir un documento no finaliza la consulta')

    def test_sin_permiso_no_entra_y_otra_clinica_tampoco(self):
        enfermera = Usuario.objects.create_user(username='enfermera', password='prueba',
                                                debe_cambiar_password=False)
        enfermera.clinicas.add(self.clinica)
        self.client.force_login(enfermera)
        self.assertEqual(self.client.get(self.url_nueva).status_code, 403)

        ajena = Usuario.objects.create_user(username='ajena', password='prueba',
                                            debe_cambiar_password=False)
        ajena.user_permissions.add(*Permission.objects.filter(
            codename__in=['view_expediente', 'add_consulta', 'change_consulta', 'view_consulta']))
        ajena.clinicas.add(Clinica.objects.create(nombre='Estética'))
        self.client.force_login(ajena)
        self.assertEqual(self.client.get(self.url_nueva).status_code, 403)


class AntecedenteTests(PruebaCore):
    """HU-EXP-07: los antecedentes son del paciente, no de la consulta."""

    def setUp(self):
        self.doctor = Usuario.objects.create_user(
            username='medica2', password='prueba', first_name='Ana', last_name='Médica',
            debe_cambiar_password=False)
        self.doctor.user_permissions.add(*Permission.objects.filter(codename__in=[
            'view_expediente', 'view_antecedente', 'add_antecedente', 'change_antecedente']))
        self.clinica = Clinica.objects.create(nombre='ProSalud')
        self.doctor.clinicas.add(self.clinica)
        self.persona = Persona.objects.create(nombres='Paciente', apellidos='Ficticio')
        self.expediente = Expediente.objects.create(persona=self.persona, clinica=self.clinica)
        self.client.force_login(self.doctor)
        self.url = reverse('consultas:antecedentes', args=[self.expediente.pk])

    def test_se_registra_sobre_el_expediente_no_sobre_una_consulta(self):
        respuesta = self.client.post(self.url, {'tipo': 'ALERGICO', 'detalle': 'Penicilina'})
        self.assertRedirects(respuesta, self.url)
        antecedente = Antecedente.objects.get()
        self.assertEqual(antecedente.expediente, self.expediente)
        self.assertEqual(antecedente.creado_por, self.doctor)
        self.assertEqual(antecedente.get_tipo_display(), 'Alérgico')
        # No queda atado a ninguna consulta: sobrevive a todas.
        self.assertFalse(hasattr(antecedente, 'consulta'))

    def test_los_siete_tipos_caben_en_la_columna_del_diagrama(self):
        for clave, _ in Antecedente.Tipo.choices:
            with self.subTest(tipo=clave):
                self.assertLessEqual(len(clave), 15)

    def test_detalle_vacio_no_se_guarda(self):
        self.client.post(self.url, {'tipo': 'ALERGICO', 'detalle': '   '})
        self.assertFalse(Antecedente.objects.exists())

    def test_retirar_desactiva_pero_no_elimina(self):
        self.client.post(self.url, {'tipo': 'HABITOS', 'detalle': 'Fuma'})
        antecedente = Antecedente.objects.get()
        self.client.post(reverse('consultas:desactivar_antecedente', args=[antecedente.pk]))
        antecedente.refresh_from_db()
        self.assertFalse(antecedente.activo)
        self.assertTrue(Antecedente.objects.filter(pk=antecedente.pk).exists())
        self.assertNotContains(self.client.get(self.url), 'Fuma')

    def test_aparecen_en_la_cabecera_del_expediente(self):
        self.client.post(self.url, {'tipo': 'PATOLOGICO', 'detalle': 'Diabetes tipo 2'})
        respuesta = self.client.get(reverse('pacientes:ver_expediente', args=[self.expediente.pk]))
        self.assertContains(respuesta, 'Diabetes tipo 2')
        self.assertContains(respuesta, 'Patológico')

    def test_no_se_ven_los_de_un_expediente_de_otra_clinica(self):
        otra = Clinica.objects.create(nombre='Estética')
        expediente_estetica = Expediente.objects.create(persona=self.persona, clinica=otra)
        Antecedente.objects.create(expediente=expediente_estetica, tipo='ALERGICO',
                                   detalle='Solo de Estética')
        self.assertNotContains(self.client.get(self.url), 'Solo de Estética')
        self.assertEqual(self.client.get(
            reverse('consultas:antecedentes', args=[expediente_estetica.pk])).status_code, 403)

    def test_sin_permiso_de_agregar_no_se_guarda(self):
        self.doctor.user_permissions.remove(
            *Permission.objects.filter(codename='add_antecedente'))
        self.client.force_login(Usuario.objects.get(pk=self.doctor.pk))
        respuesta = self.client.post(self.url, {'tipo': 'ALERGICO', 'detalle': 'Penicilina'})
        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(Antecedente.objects.exists())

    def test_la_consulta_ya_no_pregunta_antecedentes_ni_alergias(self):
        campos = ConsultaClinicaForm().fields
        self.assertNotIn('antecedentes', campos)
        self.assertNotIn('alergias', campos)
        self.assertEqual(list(campos), ['motivo', 'historia_enfermedad_actual', 'examen_fisico',
                                        'diagnostico', 'tratamiento', 'indicaciones'])
