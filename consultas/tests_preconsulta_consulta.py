"""Edicion de preconsulta durante la atencion y regreso al origen."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from core.models import Clinica, RegistroAuditoria
from core.tests import PruebaCore
from pacientes.models import Expediente, Persona
from seguridad.models import Usuario
from .models import Consulta, SignosVitales


class PreconsultaEnConsultaTests(PruebaCore):
    def setUp(self):
        self.doctor = Usuario.objects.create_user(username='doctor-qa', password='qa', debe_cambiar_password=False)
        self.doctor.user_permissions.add(*Permission.objects.filter(
            codename__in=['view_expediente', 'change_consulta', 'view_consulta']))
        self.enfermera = Usuario.objects.create_user(username='enfermera-qa', debe_cambiar_password=False)
        self.clinica = Clinica.objects.create(nombre='Clínica QA')
        self.doctor.clinicas.add(self.clinica)
        self.persona = Persona.objects.create(nombres='Paciente', apellidos='Ficticio', fecha_nacimiento=date(1990, 1, 1))
        self.expediente = Expediente.objects.create(persona=self.persona, clinica=self.clinica)
        self.consulta = Consulta.objects.create(expediente=self.expediente, doctor=self.doctor,
                                               inicio=timezone.now(), motivo='Motivo QA', diagnostico='Diagnóstico QA')
        self.signos = SignosVitales.objects.create(consulta=self.consulta, tomado_por=self.enfermera,
                                                  creado_por=self.enfermera, modificado_por=self.enfermera,
                                                  peso=70, presion_arterial='120/80')
        self.url = reverse('consultas:editar_preconsulta_consulta', args=[self.consulta.pk])
        self.atender = reverse('consultas:atender_consulta', args=[self.consulta.pk])
        self.detalle = reverse('consultas:ver_consulta', args=[self.consulta.pk])
        self.client.force_login(self.doctor)

    def datos(self, **extra):
        self.signos.refresh_from_db()
        return {'peso': '72', 'presion_arterial': '125/85', 'temperatura': '37.1',
                'frecuencia_cardiaca': '80', 'saturacion': '98',
                'version_preconsulta': self.signos.fecha_modificacion.isoformat(), **extra}

    def test_doctor_edita_su_atencion_sin_permiso_de_enfermeria(self):
        self.assertFalse(self.doctor.has_perm('consultas.change_signosvitales'))
        self.assertContains(self.client.get(self.atender), 'Editar preconsulta')
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('name="presion_arterial"', respuesta.json()['campos'])
        self.assertNotIn('name="talla"', respuesta.json()['campos'])
        self.assertEqual(self.client.post(self.url, self.datos()).status_code, 200)
        self.signos.refresh_from_db()
        self.assertEqual(self.signos.peso, Decimal('72'))
        self.assertEqual(self.signos.tomado_por, self.enfermera)
        self.assertEqual(self.signos.creado_por, self.enfermera)
        self.assertEqual(self.signos.modificado_por, self.doctor)
        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.diagnostico, 'Diagnóstico QA')
        self.assertIsNone(self.consulta.cierre)
        self.assertEqual(SignosVitales.objects.count(), 1)
        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.accion, RegistroAuditoria.Accion.EDITAR_PRECONSULTA)
        self.assertEqual(registro.usuario, self.doctor)
        self.assertIn('Peso: 70 kg → 72 kg', registro.detalle)

    def test_menor_recalcula_imc_y_no_cambia_presion_oculta(self):
        self.persona.fecha_nacimiento = date(timezone.localdate().year - 10, 1, 1)
        self.persona.save()
        self.assertIn('name="talla"', self.client.get(self.url).json()['campos'])
        self.assertEqual(self.client.post(self.url, self.datos(peso='30', talla='1.20', presion_arterial='invalido')).status_code, 200)
        self.signos.refresh_from_db()
        self.assertEqual(self.signos.imc, Decimal('20.8'))
        self.assertEqual(self.signos.presion_arterial, '120/80')

    def test_validacion_no_guarda_datos_ni_auditoria(self):
        for extra in [{'peso': ''}, {'peso': '-1'}, {'presion_arterial': 'abc'},
                      {'temperatura': '90'}, {'saturacion': '101'}, {'frecuencia_cardiaca': '999'}]:
            with self.subTest(extra=extra):
                self.assertEqual(self.client.post(self.url, self.datos(**extra)).status_code, 400)
        self.signos.refresh_from_db()
        self.assertEqual(self.signos.peso, 70)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_guardar_sin_cambios_no_crea_auditoria(self):
        self.assertEqual(self.client.post(self.url, self.datos(peso='70', presion_arterial='120/80',
                                                             temperatura='', frecuencia_cardiaca='', saturacion='')).status_code, 200)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_correccion_concurrente_no_se_sobrescribe(self):
        datos = self.datos()
        self.signos.peso = 75
        self.signos.save()
        SignosVitales.objects.filter(pk=self.signos.pk).update(
            fecha_modificacion=timezone.now() + timedelta(seconds=1))
        self.assertEqual(self.client.post(self.url, datos).status_code, 409)
        self.signos.refresh_from_db()
        self.assertEqual(self.signos.peso, 75)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_version_ausente_o_invalida_no_guarda(self):
        for valor in ['', 'no-fecha', '2026-99-99T00:00:00']:
            self.assertEqual(self.client.post(self.url, self.datos(version_preconsulta=valor)).status_code, 409)

    def test_despues_de_finalizar_no_se_edita_ni_se_preguarda(self):
        datos = self.datos()
        self.client.post(reverse('consultas:finalizar_consulta', args=[self.consulta.pk]))
        self.assertEqual(self.client.get(self.url).status_code, 409)
        self.assertEqual(self.client.post(self.url, datos).status_code, 409)
        self.assertEqual(self.client.post(reverse('consultas:guardar_borrador', args=[self.consulta.pk]),
                                          {'motivo': 'Sobrescribir cierre'}).status_code, 409)
        self.assertNotContains(self.client.get(self.detalle), 'Editar preconsulta')
        self.signos.refresh_from_db()
        self.assertEqual(self.signos.peso, 70)

    def test_en_espera_no_se_edita_desde_atencion(self):
        self.consulta.inicio = None
        self.consulta.save()
        self.assertEqual(self.client.get(self.url).status_code, 409)
        self.assertEqual(self.client.post(self.url, self.datos()).status_code, 409)

    def test_sin_preconsulta_no_la_crea(self):
        self.signos.delete()
        self.assertNotContains(self.client.get(self.atender), 'Editar preconsulta')
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, {'peso': '70'}).status_code, 404)

    def test_otro_doctor_no_edita_aunque_comparta_clinica(self):
        otro = Usuario.objects.create_user(username='otro-qa', debe_cambiar_password=False)
        otro.clinicas.add(self.clinica)
        otro.user_permissions.set(self.doctor.user_permissions.all())
        self.client.force_login(otro)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.datos()).status_code, 403)

    def test_sin_permiso_o_fuera_de_clinica_no_edita(self):
        self.doctor.clinicas.clear()
        self.assertEqual(self.client.post(self.url, self.datos()).status_code, 403)
        self.doctor.clinicas.add(self.clinica)
        self.doctor.user_permissions.clear()
        self.assertEqual(self.client.post(self.url, self.datos()).status_code, 403)

    def test_administradora_autorizada_edita_otra_consulta(self):
        admin = Usuario.objects.create_user(username='admin-qa', debe_cambiar_password=False)
        admin.clinicas.add(self.clinica)
        admin.user_permissions.add(*Permission.objects.filter(
            codename__in=['view_expediente', 'change_consulta', 'change_group']))
        self.client.force_login(admin)
        self.assertEqual(self.client.post(self.url, self.datos()).status_code, 200)

    def test_csrf_es_obligatorio(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.doctor)
        self.assertEqual(cliente.post(self.url, self.datos()).status_code, 403)

    def test_regresa_a_cola_tambien_despues_de_finalizar(self):
        origen = reverse('pacientes:cola_consultas') + '?vista=medico'
        self.assertEqual(self.client.get(self.atender, HTTP_REFERER='http://testserver' + origen).context['url_regresar'], origen)
        r = self.client.post(reverse('consultas:finalizar_consulta', args=[self.consulta.pk]), follow=True)
        self.assertEqual(r.context['url_regresar'], origen)
        self.assertContains(r, 'Regresar')
        self.assertContains(r, 'Ver expediente')

    def test_regresa_a_historial_con_busqueda_y_pagina(self):
        origen = reverse('consultas:historial_consultas', args=[self.expediente.pk]) + '?q=prueba&page=2'
        self.assertEqual(self.client.get(self.atender, {'volver': origen}).context['url_regresar'], origen)
        self.assertEqual(self.client.get(self.atender, HTTP_REFERER='http://testserver' + self.atender).context['url_regresar'], origen)
        self.assertEqual(self.client.get(self.detalle).context['url_regresar'], origen)

    def test_origen_se_actualiza_al_entrar_desde_otra_pantalla(self):
        self.client.get(self.atender, {'volver': reverse('pacientes:cola_consultas')})
        origen = reverse('pacientes:ver_expediente', args=[self.expediente.pk])
        self.assertEqual(self.client.get(self.atender, HTTP_REFERER='http://testserver' + origen).context['url_regresar'], origen)

    def test_rechaza_origen_externo_y_acciones_post(self):
        fallback = reverse('pacientes:cola_consultas')
        for origen in ['https://evil.invalid/pacientes/cola/', '//evil.invalid/',
                       reverse('consultas:finalizar_consulta', args=[self.consulta.pk]), self.atender,
                       '/ruta-que-no-existe/']:
            with self.subTest(origen=origen):
                self.assertEqual(self.client.get(self.atender, {'volver': origen}).context['url_regresar'], fallback)

    def test_estetica_sin_origen_regresa_al_historial(self):
        self.clinica.tipo = Clinica.Tipo.ESTETICA
        self.clinica.save()
        self.assertEqual(self.client.get(self.atender).context['url_regresar'],
                         reverse('consultas:historial_consultas', args=[self.expediente.pk]))

    def test_iniciar_desde_cola_conserva_el_origen(self):
        self.consulta.inicio = None
        self.consulta.save()
        origen = reverse('pacientes:cola_consultas') + '?vista=medico'
        r = self.client.post(reverse('consultas:iniciar_consulta', args=[self.consulta.pk]),
                             {'volver': origen}, follow=True)
        self.assertEqual(r.context['url_regresar'], origen)

    def datos_cierre(self, **extra):
        self.signos.refresh_from_db()
        return {'preconsulta_pendiente': '0',
                'preconsulta_version': self.signos.fecha_modificacion.isoformat(),
                'preconsulta_peso': '70', 'preconsulta_presion_arterial': '120/80',
                'preconsulta_temperatura': '', 'preconsulta_saturacion': '',
                'preconsulta_frecuencia_cardiaca': '', **extra}

    def test_servidor_no_finaliza_con_cambios_pendientes(self):
        respuesta = self.client.post(reverse('consultas:finalizar_consulta', args=[self.consulta.pk]),
                                     {'preconsulta_pendiente': '1'}, follow=True)
        self.assertContains(respuesta, 'Guarde los cambios de la preconsulta antes de finalizar')
        self.consulta.refresh_from_db()
        self.assertIsNone(self.consulta.cierre)

    def test_servidor_compara_preconsulta_con_lo_realmente_guardado(self):
        respuesta = self.client.post(reverse('consultas:finalizar_consulta', args=[self.consulta.pk]),
                                     self.datos_cierre(preconsulta_peso='80'), follow=True)
        self.assertContains(respuesta, 'Guarde los cambios de la preconsulta antes de finalizar')
        self.consulta.refresh_from_db()
        self.assertIsNone(self.consulta.cierre)
        self.signos.refresh_from_db()
        self.assertEqual(self.signos.peso, 70)

    def test_servidor_no_finaliza_con_una_version_anterior(self):
        datos = self.datos_cierre()
        self.signos.peso = 75
        self.signos.save()
        SignosVitales.objects.filter(pk=self.signos.pk).update(
            fecha_modificacion=timezone.now() + timedelta(seconds=1))
        respuesta = self.client.post(reverse('consultas:finalizar_consulta', args=[self.consulta.pk]), datos, follow=True)
        self.assertContains(respuesta, 'La preconsulta se actualizó')
        self.consulta.refresh_from_db()
        self.assertIsNone(self.consulta.cierre)

    def test_servidor_distingue_cero_de_un_signo_vacio(self):
        self.client.post(reverse('consultas:finalizar_consulta', args=[self.consulta.pk]),
                         self.datos_cierre(preconsulta_saturacion='0'))
        self.consulta.refresh_from_db()
        self.assertIsNone(self.consulta.cierre)

    def test_servidor_finaliza_con_preconsulta_guardada_y_sin_cambios(self):
        self.client.post(reverse('consultas:finalizar_consulta', args=[self.consulta.pk]), self.datos_cierre())
        self.consulta.refresh_from_db()
        self.assertIsNotNone(self.consulta.cierre)

    def test_expediente_regresa_a_consulta_sin_perder_origen_cola(self):
        cola = reverse('pacientes:cola_consultas') + '?vista=medico'
        self.client.get(self.atender, {'volver': cola})
        expediente = reverse('pacientes:ver_expediente', args=[self.expediente.pk])
        respuesta = self.client.get(expediente, HTTP_REFERER='http://testserver' + self.atender)
        self.assertEqual(respuesta.context['url_regresar'], self.atender + '?mantener_origen=1')
        vuelta = self.client.get(respuesta.context['url_regresar'], HTTP_REFERER='http://testserver' + expediente)
        self.assertEqual(vuelta.context['url_regresar'], cola)

    def test_expediente_regresa_a_lista_con_filtros_y_conserva_origen_al_recargar(self):
        lista = reverse('pacientes:lista_pacientes') + '?q=prueba&page=3'
        expediente = reverse('pacientes:ver_expediente', args=[self.expediente.pk])
        self.assertEqual(self.client.get(expediente, HTTP_REFERER='http://testserver' + lista).context['url_regresar'], lista)
        self.assertEqual(self.client.get(expediente, HTTP_REFERER='http://testserver' + expediente).context['url_regresar'], lista)
        # Un error de contacto vuelve a dibujar la misma pantalla sin perder el regreso.
        respuesta = self.client.post(reverse('pacientes:agregar_contacto', args=[self.expediente.pk]), {},
                                     HTTP_REFERER='http://testserver' + expediente)
        self.assertEqual(respuesta.context['url_regresar'], lista)

    def test_expediente_rechaza_origen_externo_y_acciones(self):
        expediente = reverse('pacientes:ver_expediente', args=[self.expediente.pk])
        fallback = reverse('pacientes:lista_pacientes')
        for origen in ['https://evil.invalid/', reverse('consultas:finalizar_consulta', args=[self.consulta.pk])]:
            self.assertEqual(self.client.get(expediente, {'volver': origen}).context['url_regresar'], fallback)

    def test_expediente_regresa_al_detalle_de_consulta_finalizada(self):
        self.consulta.cierre = timezone.now()
        self.consulta.save()
        expediente = reverse('pacientes:ver_expediente', args=[self.expediente.pk])
        r = self.client.get(expediente, HTTP_REFERER='http://testserver' + self.detalle)
        self.assertEqual(r.context['url_regresar'], self.detalle + '?mantener_origen=1')
