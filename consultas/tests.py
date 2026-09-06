from datetime import date, timedelta
from unittest.mock import patch
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone
from core.models import Clinica
from core.tests import PruebaCore
from pacientes.models import Persona, Expediente
from seguridad.models import Usuario
from .forms import DocumentoMedicoForm
from .models import Consulta, Incapacidad
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
        self.datos = {'tipo':'incapacidad','motivo':'Motivo revisado','dias':'5','inicio_opcion':'personalizada','fecha_inicio':'2026-09-05'}

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

    def test_emision_repetida_y_snapshot(self):
        previa=self.previa();primera=self.emitir(previa);segunda=self.emitir(previa)
        self.assertEqual(primera.url,segunda.url);self.assertEqual(Incapacidad.objects.count(),1)
        doc=Incapacidad.objects.get();self.assertEqual(doc.fecha_fin,date(2026,9,9))
        self.assertEqual(doc.consulta_id,self.consulta.pk);self.assertEqual(doc.creado_por,self.doctor)
        self.persona.nombres='Nombre cambiado';self.persona.save()
        self.doctor.first_name='Otra';self.doctor.save()
        doc.refresh_from_db();self.assertEqual(doc.paciente_nombre,'Paciente Ficticio');self.assertEqual(doc.doctor_nombre,'Ana Médica')
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
                doc=Incapacidad(tipo='incapacidad',fecha_inicio=inicio,dias=dias)
                self.assertEqual(doc.fecha_fin,fin)

    def test_hoy_se_calcula_en_servidor(self):
        datos={**self.datos,'inicio_opcion':'hoy','fecha_inicio':'2000-01-01'}
        form=DocumentoMedicoForm(datos);self.assertTrue(form.is_valid());self.assertEqual(form.cleaned_data['fecha_inicio'],timezone.localdate())

    def test_validaciones(self):
        for cambio in [{'dias':'0'},{'dias':'-1'},{'dias':'1.5'},{'dias':''},{'fecha_inicio':''},{'motivo':'  '},{'dias':'999999999999'}]:
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


class AnioDocumentoTests(PruebaCore):
    def test_anio_de_emision_en_letras(self):
        for anio, esperado in [(2026, 'dos mil veintiséis'), (2027, 'dos mil veintisiete'),
                               (2030, 'dos mil treinta'), (2031, 'dos mil treinta y uno'),
                               (2100, 'dos mil cien'), (2000, 'dos mil'),
                               (1999, 'mil novecientos noventa y nueve')]:
            with self.subTest(anio=anio):
                self.assertEqual(anio_en_letras(anio), esperado)
