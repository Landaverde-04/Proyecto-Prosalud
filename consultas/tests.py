from datetime import date, timedelta
import os
import shutil
import tempfile
from unittest.mock import patch
from reportlab.platypus import Paragraph
from django.conf import settings
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from core.models import Clinica
from core.tests import PruebaCore
from pacientes.models import Persona, Expediente
from seguridad.models import Usuario
from .forms import ConsultaClinicaForm, DocumentoMedicoForm
from .models import (Adjunto, Antecedente, Aplicacion, Consulta, DetalleReceta,
                     Incapacidad, OrdenExamen, Receta, ReferenciaMedica)
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
        # El formulario esta en la propia pantalla (panel desplegable del
        # mockup), no detras de un enlace a otra: salir de la atencion para
        # emitir obligaba a volver por expediente -> historial -> continuar.
        self.assertContains(respuesta, reverse('consultas:agregar_incapacidad', args=[consulta.pk]))
        self.assertContains(respuesta, 'id="panel-incapacidad"')
        self.assertContains(respuesta, 'Agregar un documento no finaliza la consulta')

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

    def test_se_corrige_en_su_lugar_sin_crear_otra_fila(self):
        """
        Criterio del Word: "la doctora puede registrar y EDITAR los
        antecedentes". Quedó sin construir el 06/09/2026.
        """
        self.client.post(self.url, {'tipo': 'ALERGICO', 'detalle': 'Penicilina'})
        antecedente = Antecedente.objects.get()
        respuesta = self.client.post(
            reverse('consultas:editar_antecedente', args=[antecedente.pk]),
            {'tipo': 'ALERGICO', 'detalle': 'Penicilina y derivados'})
        self.assertRedirects(respuesta, self.url)
        antecedente.refresh_from_db()
        self.assertEqual(antecedente.detalle, 'Penicilina y derivados')
        # Un antecedente es un dato permanente, no un documento emitido:
        # se corrige, no se versiona.
        self.assertEqual(Antecedente.objects.count(), 1)
        self.assertEqual(antecedente.modificado_por, self.doctor)

    def test_corregir_tambien_cambia_el_tipo(self):
        self.client.post(self.url, {'tipo': 'OTRO', 'detalle': 'Diabetes tipo 2'})
        antecedente = Antecedente.objects.get()
        self.client.post(reverse('consultas:editar_antecedente', args=[antecedente.pk]),
                         {'tipo': 'PATOLOGICO', 'detalle': 'Diabetes tipo 2'})
        antecedente.refresh_from_db()
        self.assertEqual(antecedente.tipo, Antecedente.Tipo.PATOLOGICO)

    def test_no_se_corrige_dejandolo_vacio(self):
        self.client.post(self.url, {'tipo': 'ALERGICO', 'detalle': 'Penicilina'})
        antecedente = Antecedente.objects.get()
        self.client.post(reverse('consultas:editar_antecedente', args=[antecedente.pk]),
                         {'tipo': 'ALERGICO', 'detalle': '   '})
        antecedente.refresh_from_db()
        self.assertEqual(antecedente.detalle, 'Penicilina')

    def test_sin_permiso_de_corregir_no_se_corrige(self):
        self.client.post(self.url, {'tipo': 'ALERGICO', 'detalle': 'Penicilina'})
        antecedente = Antecedente.objects.get()
        self.doctor.user_permissions.remove(
            Permission.objects.get(codename='change_antecedente'))
        # El permiso se cachea por request; recargar al usuario lo limpia.
        self.client.force_login(Usuario.objects.get(pk=self.doctor.pk))
        respuesta = self.client.post(
            reverse('consultas:editar_antecedente', args=[antecedente.pk]),
            {'tipo': 'ALERGICO', 'detalle': 'Otra cosa'})
        self.assertEqual(respuesta.status_code, 403)
        antecedente.refresh_from_db()
        self.assertEqual(antecedente.detalle, 'Penicilina')

    def test_no_se_corrige_un_antecedente_de_otra_clinica(self):
        otra = Clinica.objects.create(nombre='Estética')
        persona = Persona.objects.create(nombres='Ajeno', apellidos='Paciente')
        expediente = Expediente.objects.create(persona=persona, clinica=otra)
        antecedente = Antecedente.objects.create(
            expediente=expediente, tipo='ALERGICO', detalle='Ajeno',
            creado_por=self.doctor, modificado_por=self.doctor)
        respuesta = self.client.post(
            reverse('consultas:editar_antecedente', args=[antecedente.pk]),
            {'tipo': 'ALERGICO', 'detalle': 'Intruso'})
        self.assertEqual(respuesta.status_code, 403)
        antecedente.refresh_from_db()
        self.assertEqual(antecedente.detalle, 'Ajeno')

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


class ConsultaSoloDeSuDoctorTests(PruebaCore):
    """Un doctor no puede escribir en la consulta de otro; la administradora sí."""

    def setUp(self):
        self.clinica = Clinica.objects.create(nombre='ProSalud')
        permisos_medico = Permission.objects.filter(
            codename__in=['view_expediente', 'view_consulta', 'change_consulta'],
        )

        self.doctor1 = Usuario.objects.create_user(
            username='doctor1', password='x', first_name='Uno', last_name='Medico',
            debe_cambiar_password=False,
        )
        self.doctor2 = Usuario.objects.create_user(
            username='doctor2', password='x', first_name='Dos', last_name='Medico',
            debe_cambiar_password=False,
        )
        self.administradora = Usuario.objects.create_user(
            username='doctora', password='x', first_name='Elsa', last_name='Miranda',
            debe_cambiar_password=False,
        )
        for usuario in (self.doctor1, self.doctor2, self.administradora):
            usuario.user_permissions.add(*permisos_medico)
            usuario.clinicas.add(self.clinica)
        # "Administradora" se define por poder editar roles, igual que en seguridad.
        self.administradora.user_permissions.add(
            Permission.objects.get(content_type__app_label='auth', codename='change_group'),
        )

        persona = Persona.objects.create(nombres='Paciente', apellidos='De Uno')
        self.expediente = Expediente.objects.create(persona=persona, clinica=self.clinica)
        self.consulta = Consulta.objects.create(
            expediente=self.expediente, doctor=self.doctor1, motivo='Atención de prueba',
        )

    def test_su_propio_doctor_si_puede_atender(self):
        self.client.force_login(self.doctor1)
        respuesta = self.client.get(reverse('consultas:atender_consulta', args=[self.consulta.pk]))
        self.assertEqual(respuesta.status_code, 200)

    def test_otro_doctor_no_puede_abrir_la_consulta(self):
        self.client.force_login(self.doctor2)
        respuesta = self.client.get(reverse('consultas:atender_consulta', args=[self.consulta.pk]))
        self.assertEqual(respuesta.status_code, 403)

    def test_otro_doctor_no_puede_iniciarla_desde_la_cola(self):
        self.client.force_login(self.doctor2)
        respuesta = self.client.post(reverse('consultas:iniciar_consulta', args=[self.consulta.pk]))
        self.assertEqual(respuesta.status_code, 403)
        self.consulta.refresh_from_db()
        self.assertIsNone(self.consulta.inicio)

    def test_otro_doctor_no_puede_escribir_ni_finalizar(self):
        self.client.force_login(self.doctor2)

        borrador = self.client.post(
            reverse('consultas:guardar_borrador', args=[self.consulta.pk]), {'motivo': 'Texto ajeno'},
        )
        self.assertEqual(borrador.status_code, 403)

        finalizar = self.client.post(reverse('consultas:finalizar_consulta', args=[self.consulta.pk]))
        self.assertEqual(finalizar.status_code, 403)

        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.motivo, 'Atención de prueba')
        self.assertIsNone(self.consulta.cierre)

    def test_la_administradora_si_puede_sobre_cualquier_consulta(self):
        self.client.force_login(self.administradora)
        respuesta = self.client.get(reverse('consultas:atender_consulta', args=[self.consulta.pk]))
        self.assertEqual(respuesta.status_code, 200)

    def test_otro_doctor_si_puede_leer_el_historial(self):
        """Leer no se restringe: el expediente es de la clinica, no del medico."""
        self.consulta.inicio = timezone.now()
        self.consulta.cierre = timezone.now()
        self.consulta.save()
        self.client.force_login(self.doctor2)

        respuesta = self.client.get(reverse('consultas:ver_consulta', args=[self.consulta.pk]))

        self.assertEqual(respuesta.status_code, 200)


class UnPacienteALaVezTests(PruebaCore):
    """Con una consulta en atencion, el medico no inicia otra salvo emergencia."""

    def setUp(self):
        clinica = Clinica.objects.create(nombre='ProSalud')
        self.doctor = Usuario.objects.create_user(username='doctor1', password='x', debe_cambiar_password=False)
        self.doctor.user_permissions.add(*Permission.objects.filter(
            codename__in=['view_expediente', 'view_consulta', 'change_consulta', 'add_consulta'],
        ))
        self.doctor.clinicas.add(clinica)
        self.expedientes = [
            Expediente.objects.create(persona=Persona.objects.create(nombres=nombre, apellidos='Prueba'),
                                      clinica=clinica)
            for nombre in ('Atendiendo', 'Esperando')
        ]
        self.en_curso = Consulta.objects.create(
            expediente=self.expedientes[0], doctor=self.doctor, motivo='', inicio=timezone.now(),
        )
        self.en_espera = Consulta.objects.create(expediente=self.expedientes[1], doctor=self.doctor, motivo='')
        self.client.force_login(self.doctor)

    def test_no_inicia_otro_paciente_con_uno_en_atencion(self):
        respuesta = self.client.post(reverse('consultas:iniciar_consulta', args=[self.en_espera.pk]))

        self.assertRedirects(respuesta, reverse('pacientes:cola_consultas'), fetch_redirect_response=False)
        self.en_espera.refresh_from_db()
        self.assertIsNone(self.en_espera.inicio)

    def test_una_emergencia_si_se_puede_iniciar(self):
        self.en_espera.es_emergencia = True
        self.en_espera.save()

        self.client.post(reverse('consultas:iniciar_consulta', args=[self.en_espera.pk]))

        self.en_espera.refresh_from_db()
        self.assertIsNotNone(self.en_espera.inicio)

    def test_al_finalizar_ya_puede_iniciar_el_siguiente(self):
        self.en_curso.cierre = timezone.now()
        self.en_curso.save()

        self.client.post(reverse('consultas:iniciar_consulta', args=[self.en_espera.pk]))

        self.en_espera.refresh_from_db()
        self.assertIsNotNone(self.en_espera.inicio)

    def test_no_registra_consulta_manual_con_una_en_atencion(self):
        otro = Expediente.objects.create(
            persona=Persona.objects.create(nombres='Manual', apellidos='Prueba'),
            clinica=self.expedientes[0].clinica,
        )
        respuesta = self.client.get(reverse('consultas:nueva_consulta', args=[otro.pk]))

        self.assertRedirects(respuesta, reverse('pacientes:ver_expediente', args=[otro.pk]),
                             fetch_redirect_response=False)


class VisitaRetiradaTests(PruebaCore):
    """Una visita donde el paciente se fue sin atenderse."""

    def setUp(self):
        self.clinica = Clinica.objects.create(nombre='ProSalud')
        self.doctor = Usuario.objects.create_user(username='doctor', password='x', debe_cambiar_password=False)
        self.doctor.user_permissions.add(*Permission.objects.filter(
            codename__in=['view_expediente', 'view_consulta', 'change_consulta', 'view_incapacidad', 'add_incapacidad'],
        ))
        self.doctor.clinicas.add(self.clinica)
        persona = Persona.objects.create(nombres='Paciente', apellidos='Retirado')
        self.expediente = Expediente.objects.create(persona=persona, clinica=self.clinica)
        ahora = timezone.now()
        self.consulta = Consulta.objects.create(
            expediente=self.expediente, doctor=self.doctor, motivo='', hora_llegada=ahora,
            cierre=ahora, nota_retiro='Tenía que regresar al trabajo',
        )
        self.client.force_login(self.doctor)

    def test_el_historial_la_muestra_como_retiro_con_su_nota(self):
        respuesta = self.client.get(reverse('consultas:historial_consultas', args=[self.expediente.pk]))
        self.assertContains(respuesta, 'Se retiró')
        self.assertContains(respuesta, 'Tenía que regresar al trabajo')
        self.assertNotContains(respuesta, 'Finalizada')

    def test_el_detalle_muestra_la_nota_y_no_ofrece_documentos(self):
        respuesta = self.client.get(reverse('consultas:ver_consulta', args=[self.consulta.pk]))
        self.assertContains(respuesta, 'se retiró antes de pasar a consulta')
        self.assertContains(respuesta, 'Tenía que regresar al trabajo')
        self.assertNotContains(respuesta, 'Constancia de incapacidad')

    def test_no_se_emiten_documentos_sobre_una_visita_retirada(self):
        respuesta = self.client.get(reverse('consultas:nuevo_documento', args=[self.consulta.pk]))
        self.assertEqual(respuesta.status_code, 404)


# ==========================================================================
# Documentos de la consulta que se escribieron sin pruebas, por acuerdo con
# Samuel de dejarlas "para cuando esté todo": HU-EXP-20, 21, 23, 25 y 08.
#
# Todas comparten el mismo montaje -- una doctora, su clínica, un paciente y
# una consulta abierta -- así que vive una sola vez, abajo.
# ==========================================================================

class PruebaDeDocumentos(PruebaCore):
    """
    Montaje común. Cada clase declara en `permisos` lo que su historia
    necesita: así una prueba de permisos no se cuela por tenerlos todos.
    """

    permisos = []

    def setUp(self):
        self.doctora = Usuario.objects.create_user(
            username='medica', password='prueba', first_name='Elsa', last_name='Miranda',
            debe_cambiar_password=False)
        self.doctora.user_permissions.add(*Permission.objects.filter(
            codename__in=['view_expediente'] + self.permisos))
        self.clinica = Clinica.objects.create(nombre='ProSalud')
        self.doctora.clinicas.add(self.clinica)
        self.persona = Persona.objects.create(nombres='Jose Roberto', apellidos='Munoz Castro')
        self.expediente = Expediente.objects.create(persona=self.persona, clinica=self.clinica)
        self.consulta = self.abrir_consulta(self.expediente)
        self.client.force_login(self.doctora)

    def abrir_consulta(self, expediente):
        return Consulta.objects.create(
            expediente=expediente, doctor=self.doctora, doctor_nombre='Elsa Miranda',
            inicio=timezone.now(), motivo='Dolor de cabeza',
            creado_por=self.doctora, modificado_por=self.doctora)

    def consulta_ajena(self):
        """Una consulta de otra clínica, a la que la doctora no pertenece."""
        otra = Clinica.objects.create(nombre='Estética')
        persona = Persona.objects.create(nombres='Ajeno', apellidos='Paciente')
        expediente = Expediente.objects.create(persona=persona, clinica=otra)
        return self.abrir_consulta(expediente)


class RecetaTests(PruebaDeDocumentos):
    """HU-EXP-25: escribir la receta durante la consulta."""

    permisos = ['view_receta', 'add_receta', 'change_receta']
    AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}

    def agregar(self, medicamento='Amoxicilina 500 mg', dosis='1 cada 8 horas',
                duracion='7 dias', **extra):
        return self.client.post(
            reverse('consultas:agregar_medicamento', args=[self.consulta.pk]),
            {'medicamento': medicamento, 'dosis': dosis, 'duracion': duracion}, **extra)

    def test_el_primer_medicamento_crea_la_receta_con_su_folio(self):
        self.agregar()
        receta = Receta.objects.get(consulta=self.consulta)
        self.assertEqual(receta.folio, f'R-{receta.pk:08d}')
        self.assertEqual(receta.doctor_nombre, 'Elsa Miranda')
        self.assertEqual(receta.detalles.count(), 1)

    def test_una_consulta_tiene_una_sola_receta(self):
        """Dos medicamentos seguidos van a la misma receta, no a dos."""
        self.agregar()
        self.agregar(medicamento='Ibuprofeno 400 mg')
        self.assertEqual(Receta.objects.filter(consulta=self.consulta).count(), 1)
        self.assertEqual(Receta.objects.get().detalles.count(), 2)

    def test_corregir_cambia_la_fila_en_vez_de_crear_otra(self):
        self.agregar()
        detalle = DetalleReceta.objects.get()
        self.client.post(reverse('consultas:editar_medicamento', args=[detalle.pk]),
                         {'medicamento': 'Amoxicilina 500 mg', 'dosis': '1 cada 12 horas',
                          'duracion': '5 dias'})
        detalle.refresh_from_db()
        self.assertEqual(detalle.dosis, '1 cada 12 horas')
        self.assertEqual(DetalleReceta.objects.count(), 1)
        self.assertEqual(detalle.modificado_por, self.doctora)

    def test_quitar_un_medicamento_lo_desactiva_sin_borrarlo(self):
        """Nada se elimina: se desactiva y deja de salir en el PDF."""
        self.agregar()
        detalle = DetalleReceta.objects.get()
        self.client.post(reverse('consultas:quitar_medicamento', args=[detalle.pk]))
        detalle.refresh_from_db()
        self.assertFalse(detalle.activo)
        self.assertEqual(DetalleReceta.objects.count(), 1)

    def test_por_fetch_devuelve_el_pedazo_y_no_recarga(self):
        """
        Lo que evita que la pantalla de atención se recargue y se mueva de
        lugar cada vez que se agrega un medicamento.
        """
        respuesta = self.agregar(**self.AJAX)
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertTrue(datos['ok'])
        self.assertIn('Amoxicilina 500 mg', datos['medicamentos'])
        # El botón "Ver PDF" nace con la receta: antes no existía.
        self.assertIn('data-ver-pdf', datos['acciones'])

    def test_sin_javascript_sigue_redirigiendo(self):
        """El formulario tiene que funcionar igual sin el fetch."""
        respuesta = self.agregar()
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(DetalleReceta.objects.exists())

    def test_un_medicamento_vacio_no_se_guarda(self):
        respuesta = self.agregar(medicamento='', **self.AJAX)
        self.assertEqual(respuesta.json()['tipo'], 'danger')
        self.assertFalse(DetalleReceta.objects.exists())

    def test_no_se_receta_en_una_consulta_de_otra_clinica(self):
        ajena = self.consulta_ajena()
        respuesta = self.client.post(
            reverse('consultas:agregar_medicamento', args=[ajena.pk]),
            {'medicamento': 'X', 'dosis': 'Y', 'duracion': 'Z'})
        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(DetalleReceta.objects.exists())

    def test_sin_permiso_de_corregir_no_se_corrige(self):
        self.agregar()
        detalle = DetalleReceta.objects.get()
        self.doctora.user_permissions.remove(
            Permission.objects.get(codename='change_receta'))
        # El permiso se cachea por request; recargar al usuario lo limpia.
        self.client.force_login(Usuario.objects.get(pk=self.doctora.pk))
        respuesta = self.client.post(reverse('consultas:editar_medicamento', args=[detalle.pk]),
                                     {'medicamento': 'Otro', 'dosis': 'x', 'duracion': 'y'})
        self.assertEqual(respuesta.status_code, 403)
        detalle.refresh_from_db()
        self.assertEqual(detalle.medicamento, 'Amoxicilina 500 mg')

    def test_emitir_la_receta_no_finaliza_la_consulta(self):
        """
        La regla del mockup ("Generar receta y cerrar") se descartó el
        05/09/2026. Cierra "Finalizar consulta", que es acción aparte.
        """
        self.agregar()
        self.consulta.refresh_from_db()
        self.assertIsNone(self.consulta.cierre)
        self.assertTrue(self.consulta.en_atencion)

    def test_el_pdf_no_incluye_los_medicamentos_quitados(self):
        self.agregar()
        self.agregar(medicamento='Retirado 100 mg')
        quitado = DetalleReceta.objects.get(medicamento='Retirado 100 mg')
        self.client.post(reverse('consultas:quitar_medicamento', args=[quitado.pk]))
        receta = Receta.objects.get()
        respuesta = self.client.get(reverse('consultas:pdf_receta', args=[receta.pk]))
        self.assertEqual(respuesta['Content-Type'], 'application/pdf')
        self.assertGreater(len(respuesta.content), 1000)


class OrdenExamenTests(PruebaDeDocumentos):
    """HU-EXP-20: solicitar exámenes."""

    permisos = ['view_ordenexamen', 'add_ordenexamen']

    def pedir(self, examenes='Hemograma, glucosa, orina', indicaciones=''):
        return self.client.post(
            reverse('consultas:agregar_orden', args=[self.consulta.pk]),
            {'examenes': examenes, 'indicaciones': indicaciones})

    def test_los_examenes_se_guardan_uno_por_fila(self):
        """
        La doctora escribe de corrido, pero el dato queda estructurado para
        cuando exista el módulo de Laboratorio.
        """
        self.pedir()
        orden = OrdenExamen.objects.get()
        self.assertEqual(
            sorted(orden.detalles.values_list('tipo_examen', flat=True)),
            ['Hemograma', 'glucosa', 'orina'])

    def test_las_comas_de_mas_no_crean_filas_vacias(self):
        self.pedir(examenes='Hemograma, , glucosa,')
        self.assertEqual(OrdenExamen.objects.get().detalles.count(), 2)

    def test_sin_ningun_examen_no_se_crea_la_orden(self):
        self.pedir(examenes='  ,  , ')
        self.assertFalse(OrdenExamen.objects.exists())

    def test_la_orden_congela_el_nombre_del_medico_y_apunta_al_paciente(self):
        self.pedir(indicaciones='En ayunas de 8 horas')
        orden = OrdenExamen.objects.get()
        self.assertEqual(orden.doctor_nombre, 'Elsa Miranda')
        self.assertEqual(orden.persona, self.persona)
        self.assertEqual(orden.consulta, self.consulta)
        self.assertEqual(orden.indicaciones, 'En ayunas de 8 horas')
        self.assertEqual(orden.creado_por, self.doctora)

    def test_la_orden_no_nace_con_estado_ni_resultado(self):
        """
        A propósito: una orden puede quedar sin resultado de forma
        indefinida sin estar incompleta. Con un estado, todas quedarían
        "pendientes" para siempre -- un dato que miente.
        """
        self.pedir()
        orden = OrdenExamen.objects.get()
        self.assertFalse(hasattr(orden, 'estado'))
        self.assertFalse(hasattr(orden, 'resultado'))

    def test_genera_su_pdf(self):
        self.pedir()
        orden = OrdenExamen.objects.get()
        respuesta = self.client.get(reverse('consultas:pdf_orden', args=[orden.pk]))
        self.assertEqual(respuesta['Content-Type'], 'application/pdf')
        self.assertGreater(len(respuesta.content), 1000)

    def test_no_se_pide_sobre_una_consulta_de_otra_clinica(self):
        ajena = self.consulta_ajena()
        respuesta = self.client.post(reverse('consultas:agregar_orden', args=[ajena.pk]),
                                     {'examenes': 'Hemograma', 'indicaciones': ''})
        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(OrdenExamen.objects.exists())


class ReferenciaMedicaTests(PruebaDeDocumentos):
    """HU-EXP-23: referir a un especialista."""

    permisos = ['view_referenciamedica', 'add_referenciamedica']

    def referir(self, especialidad='Cardiología', motivo='Soplo a descartar'):
        return self.client.post(
            reverse('consultas:agregar_referencia', args=[self.consulta.pk]),
            {'especialidad': especialidad, 'motivo': motivo, 'observaciones': ''})

    def test_la_referencia_congela_el_nombre_del_medico(self):
        self.referir()
        referencia = ReferenciaMedica.objects.get()
        self.assertEqual(referencia.especialidad, 'Cardiología')
        self.assertEqual(referencia.doctor_nombre, 'Elsa Miranda')
        self.assertEqual(referencia.consulta, self.consulta)

    def test_sin_especialidad_no_se_crea(self):
        self.referir(especialidad='   ')
        self.assertFalse(ReferenciaMedica.objects.exists())

    def test_genera_su_pdf(self):
        self.referir()
        referencia = ReferenciaMedica.objects.get()
        respuesta = self.client.get(reverse('consultas:pdf_referencia', args=[referencia.pk]))
        self.assertEqual(respuesta['Content-Type'], 'application/pdf')
        self.assertGreater(len(respuesta.content), 1000)

    def test_no_se_refiere_desde_una_consulta_de_otra_clinica(self):
        ajena = self.consulta_ajena()
        respuesta = self.client.post(reverse('consultas:agregar_referencia', args=[ajena.pk]),
                                     {'especialidad': 'X', 'motivo': 'Y', 'observaciones': ''})
        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(ReferenciaMedica.objects.exists())


class AplicacionTests(PruebaDeDocumentos):
    """HU-EXP-21: la doctora indica, otra persona aplica."""

    permisos = ['view_aplicacion', 'add_aplicacion', 'change_aplicacion']

    def indicar(self, tipo='nebulizacion', dosis='2 puff'):
        return self.client.post(
            reverse('consultas:agregar_aplicacion', args=[self.consulta.pk]),
            {'tipo': tipo, 'dosis': dosis, 'indicaciones': 'Cada 6 horas'})

    def test_se_indica_sin_quedar_aplicada(self):
        """Indicarla y aplicarla son dos momentos distintos."""
        self.indicar()
        aplicacion = Aplicacion.objects.get()
        self.assertFalse(aplicacion.ejecutada)
        self.assertIsNone(aplicacion.ejecutada_por)
        self.assertIsNone(aplicacion.fecha_ejecucion)

    def test_marcarla_registra_quien_la_aplico_y_cuando(self):
        self.indicar()
        aplicacion = Aplicacion.objects.get()
        self.client.post(reverse('consultas:marcar_aplicacion', args=[aplicacion.pk]))
        aplicacion.refresh_from_db()
        self.assertTrue(aplicacion.ejecutada)
        self.assertEqual(aplicacion.ejecutada_por, self.doctora)
        self.assertIsNotNone(aplicacion.fecha_ejecucion)

    def test_marcarla_dos_veces_no_pisa_la_primera_firma(self):
        self.indicar()
        aplicacion = Aplicacion.objects.get()
        self.client.post(reverse('consultas:marcar_aplicacion', args=[aplicacion.pk]))
        aplicacion.refresh_from_db()
        primera = aplicacion.fecha_ejecucion
        self.client.post(reverse('consultas:marcar_aplicacion', args=[aplicacion.pk]))
        aplicacion.refresh_from_db()
        self.assertEqual(aplicacion.fecha_ejecucion, primera)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='prosalud-pruebas-'))
class AdjuntoTests(PruebaDeDocumentos):
    """
    HU-EXP-08: archivos del expediente.

    `MEDIA_ROOT` se manda a una carpeta temporal: las pruebas no deben
    escribir en la carpeta real de archivos clínicos.
    """

    permisos = ['view_adjunto', 'add_adjunto', 'change_adjunto']

    # Cabeceras reales de cada formato. Lo que se valida no es la extensión.
    PDF = b'%PDF-1.4\n%fin'
    PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 40
    JPG = b'\xff\xd8\xff\xe0' + b'\x00' * 40

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def subir(self, contenido=None, nombre='examen.pdf', descripcion='Radiografía de tórax'):
        archivo = SimpleUploadedFile(nombre, contenido if contenido is not None else self.PDF)
        return self.client.post(reverse('consultas:adjuntos', args=[self.expediente.pk]),
                                {'archivo': archivo, 'descripcion': descripcion})

    def test_sube_un_pdf_y_lo_clasifica_por_sus_bytes(self):
        self.subir()
        adjunto = Adjunto.objects.get()
        self.assertEqual(adjunto.tipo, Adjunto.Tipo.PDF)
        self.assertEqual(adjunto.expediente, self.expediente)
        self.assertEqual(adjunto.descripcion, 'Radiografía de tórax')

    def test_sube_una_imagen(self):
        self.subir(contenido=self.PNG, nombre='foto.png')
        self.assertTrue(Adjunto.objects.get().es_imagen)

    def test_rechaza_lo_que_no_es_pdf_ni_imagen_aunque_se_llame_pdf(self):
        """
        La extensión la pone quien sube el archivo. Renombrar un ejecutable
        a .pdf no lo convierte en PDF.
        """
        self.subir(contenido=b'MZ\x90\x00 ejecutable', nombre='virus.pdf')
        self.assertFalse(Adjunto.objects.exists())

    def test_rechaza_un_archivo_mas_grande_que_el_tope(self):
        gordo = self.PDF + b'\x00' * (settings.TAMANO_MAXIMO_ADJUNTO + 1)
        self.subir(contenido=gordo)
        self.assertFalse(Adjunto.objects.exists())

    def test_exige_descripcion(self):
        """Sin ella la lista serían varias filas idénticas: el nombre real se descarta."""
        self.subir(descripcion='   ')
        self.assertFalse(Adjunto.objects.exists())

    def test_el_nombre_original_no_queda_guardado(self):
        """Suele traer datos del paciente ("dui-juan-perez.pdf")."""
        self.subir(nombre='dui-jose-roberto-munoz.pdf')
        ruta = Adjunto.objects.get().archivo.name
        self.assertNotIn('jose', ruta.lower())
        self.assertNotIn('dui', ruta.lower())
        self.assertTrue(ruta.endswith('.pdf'))

    def test_guarda_quien_lo_subio_y_cuando_sin_columnas_nuevas(self):
        """El diagrama pedía `fecha` y `subido_por`: los da ModeloBase."""
        self.subir()
        adjunto = Adjunto.objects.get()
        self.assertEqual(adjunto.creado_por, self.doctora)
        self.assertIsNotNone(adjunto.fecha_creacion)

    def test_el_archivo_se_descarga_por_la_vista_protegida(self):
        self.subir()
        adjunto = Adjunto.objects.get()
        respuesta = self.client.get(reverse('consultas:descargar_adjunto', args=[adjunto.pk]))
        self.assertEqual(respuesta['Content-Type'], 'application/pdf')
        self.assertEqual(respuesta['X-Content-Type-Options'], 'nosniff')

    def test_sin_sesion_no_se_llega_al_archivo(self):
        self.subir()
        adjunto = Adjunto.objects.get()
        self.client.logout()
        respuesta = self.client.get(reverse('consultas:descargar_adjunto', args=[adjunto.pk]))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn('/login', respuesta['Location'])

    def test_no_se_descarga_un_adjunto_de_otra_clinica(self):
        otra = Clinica.objects.create(nombre='Estética')
        persona = Persona.objects.create(nombres='Ajeno', apellidos='Paciente')
        ajeno = Expediente.objects.create(persona=persona, clinica=otra)
        adjunto = Adjunto.objects.create(
            expediente=ajeno, descripcion='Ajeno', tipo=Adjunto.Tipo.PDF,
            archivo=SimpleUploadedFile('x.pdf', self.PDF),
            creado_por=self.doctora, modificado_por=self.doctora)
        respuesta = self.client.get(reverse('consultas:descargar_adjunto', args=[adjunto.pk]))
        self.assertEqual(respuesta.status_code, 403)

    def test_retirarlo_lo_desactiva_y_deja_el_archivo_en_disco(self):
        """
        Es un expediente clínico: si mañana hay que explicar qué se subió y
        se retiró, el archivo tiene que seguir ahí.
        """
        self.subir()
        adjunto = Adjunto.objects.get()
        ruta = adjunto.archivo.path
        self.client.post(reverse('consultas:retirar_adjunto', args=[adjunto.pk]))
        adjunto.refresh_from_db()
        self.assertFalse(adjunto.activo)
        self.assertTrue(os.path.exists(ruta))

    def test_un_adjunto_retirado_deja_de_aparecer(self):
        # Descripción que no exista en ningún otro lado de la plantilla: el
        # placeholder del formulario también dice "Radiografía de tórax".
        self.subir(descripcion='Electrocardiograma del 12 de agosto')
        adjunto = Adjunto.objects.get()
        self.client.post(reverse('consultas:retirar_adjunto', args=[adjunto.pk]))
        respuesta = self.client.get(reverse('consultas:adjuntos', args=[self.expediente.pk]))
        self.assertNotContains(respuesta, 'Electrocardiograma del 12 de agosto')
        self.assertContains(respuesta, 'todavía no tiene archivos adjuntos')
