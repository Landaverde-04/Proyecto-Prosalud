import json

from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone

from core.models import Clinica
from core.tests import PruebaCore
from pacientes.models import Expediente, Persona
from seguridad.models import Usuario
from .models import AtencionEstetica, FichaEstetica, ProcedimientoEstetico, SesionProcedimiento


class PruebaDeFicha(PruebaCore):
    """Montaje común: una paciente con expediente en Estética y la doctora trabajando ahí."""

    AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}

    def setUp(self):
        self.prosalud = Clinica.objects.create(nombre='ProSalud')
        self.estetica = Clinica.objects.create(nombre='Estética', tipo=Clinica.Tipo.ESTETICA)
        self.doctora = Usuario.objects.create_user(
            username='medica', password='prueba', first_name='Elsa', last_name='Miranda',
            debe_cambiar_password=False)
        self.doctora.user_permissions.add(Permission.objects.get(codename='view_expediente'))
        self.doctora.clinicas.add(self.prosalud, self.estetica)
        self.persona = Persona.objects.create(nombres='Rosa María', apellidos='Campos Díaz', telefono='7000-0000')
        self.expediente = Expediente.objects.create(persona=self.persona, clinica=self.estetica)
        self.client.force_login(self.doctora)
        self.trabajar_en(self.estetica)
        self.url = reverse('estetica:ficha', args=[self.expediente.pk])
        self.url_guardar = reverse('estetica:guardar_ficha', args=[self.expediente.pk])

    def trabajar_en(self, clinica):
        self.client.post(reverse('core:cambiar_clinica'), {'clinica': clinica.pk})

    def guardar(self, **datos):
        return self.client.post(self.url_guardar, datos, **self.AJAX)


class FichaEsteticaTests(PruebaDeFicha):
    """HU-EST-01: la ficha de ingreso de la paciente en la clínica estética."""

    def test_la_pantalla_abre_vacia_con_los_datos_de_la_persona(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Rosa María Campos Díaz')
        self.assertContains(respuesta, 'Todavía sin guardar')
        self.assertFalse(FichaEstetica.objects.exists())

    def test_el_primer_guardado_crea_la_ficha(self):
        respuesta = self.guardar(ocupacion='Contadora', como_conocio='facebook')
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertTrue(datos['ok'])
        self.assertRegex(datos['hora'], r'^\d\d:\d\d$')
        ficha = FichaEstetica.objects.get()
        self.assertEqual(ficha.expediente, self.expediente)
        self.assertEqual(ficha.ocupacion, 'Contadora')
        self.assertEqual(ficha.como_conocio, 'facebook')
        self.assertEqual(ficha.creado_por, self.doctora)
        self.assertEqual(ficha.modificado_por, self.doctora)

    def test_todos_los_campos_se_pueden_dejar_vacios(self):
        respuesta = self.guardar(estado_civil='', religion='', ocupacion='', email='', direccion='',
                                 medico='', como_conocio='', referido_por='')
        self.assertEqual(respuesta.status_code, 200)
        ficha = FichaEstetica.objects.get()
        self.assertEqual((ficha.religion, ficha.email, ficha.como_conocio), ('', '', ''))

    def test_los_siguientes_guardados_corrigen_la_misma_ficha(self):
        self.guardar(ocupacion='Contadora')
        self.guardar(ocupacion='Abogada', email='rosa@correo.com')
        self.assertEqual(FichaEstetica.objects.count(), 1)
        ficha = FichaEstetica.objects.get()
        self.assertEqual(ficha.ocupacion, 'Abogada')
        self.assertEqual(ficha.email, 'rosa@correo.com')

    def test_al_recargar_se_ve_lo_guardado(self):
        self.guardar(estado_civil='Casada', direccion='Col. Escalón', como_conocio='referido_paciente',
                     referido_por='Ana Pérez')
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, 'value="Casada"')
        self.assertContains(respuesta, 'value="Col. Escalón"')
        self.assertContains(respuesta, 'value="Ana Pérez"')
        self.assertContains(respuesta, '<option value="referido_paciente" selected>', html=False)
        self.assertContains(respuesta, 'Guardada el')

    def test_un_correo_mal_escrito_no_se_guarda_y_lo_dice(self):
        respuesta = self.guardar(email='no-es-correo')
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('Correo electrónico', respuesta.json()['mensaje'])
        self.assertFalse(FichaEstetica.objects.exists())

    def test_una_opcion_desconocida_de_como_conocio_se_rechaza(self):
        self.assertEqual(self.guardar(como_conocio='tiktok').status_code, 400)
        self.assertFalse(FichaEstetica.objects.exists())

    def test_sin_javascript_guarda_y_vuelve_al_expediente(self):
        respuesta = self.client.post(self.url_guardar, {'ocupacion': 'Contadora'})
        self.assertRedirects(respuesta, reverse('pacientes:ver_expediente', args=[self.expediente.pk]))
        self.assertEqual(FichaEstetica.objects.get().ocupacion, 'Contadora')

    def test_un_expediente_de_la_clinica_medica_no_tiene_ficha(self):
        medico = Expediente.objects.create(persona=self.persona, clinica=self.prosalud)
        self.trabajar_en(self.prosalud)
        self.assertEqual(self.client.get(reverse('estetica:ficha', args=[medico.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('estetica:guardar_ficha', args=[medico.pk]),
                                          {'ocupacion': 'x'}, **self.AJAX).status_code, 404)

    def test_con_prosalud_activa_no_se_abre_ni_se_guarda(self):
        """Criterio 5: solo con la clínica Estética activa."""
        self.trabajar_en(self.prosalud)
        respuesta = self.client.get(self.url)
        self.assertRedirects(respuesta, reverse('pacientes:ver_expediente', args=[self.expediente.pk]),
                             fetch_redirect_response=False)
        self.assertEqual(self.guardar(ocupacion='x').status_code, 409)
        self.assertFalse(FichaEstetica.objects.exists())

    def test_quien_no_es_de_la_clinica_no_entra(self):
        ajena = Usuario.objects.create_user(username='ajena', password='prueba', debe_cambiar_password=False)
        ajena.user_permissions.add(Permission.objects.get(codename='view_expediente'))
        ajena.clinicas.add(self.prosalud)
        self.client.force_login(ajena)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.guardar(ocupacion='x').status_code, 403)

    def test_sin_permiso_de_expediente_no_entra(self):
        """Solo quien abre expedientes (doctores) llena la ficha; la secretaria no."""
        self.doctora.user_permissions.clear()
        self.client.force_login(Usuario.objects.get(pk=self.doctora.pk))
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.guardar(ocupacion='x').status_code, 403)

    # --- La tarjeta en el expediente (ver_expediente.html, de Kevin) ---

    def test_el_expediente_de_estetica_ofrece_la_ficha(self):
        respuesta = self.client.get(reverse('pacientes:ver_expediente', args=[self.expediente.pk]))
        self.assertContains(respuesta, self.url)
        self.assertContains(respuesta, 'Completar ficha')
        self.guardar(ocupacion='Contadora')
        respuesta = self.client.get(reverse('pacientes:ver_expediente', args=[self.expediente.pk]))
        self.assertContains(respuesta, 'Ver y corregir')

    def test_el_expediente_medico_no_la_ofrece(self):
        medico = Expediente.objects.create(persona=self.persona, clinica=self.prosalud)
        self.trabajar_en(self.prosalud)
        respuesta = self.client.get(reverse('pacientes:ver_expediente', args=[medico.pk]))
        self.assertNotContains(respuesta, 'Ficha estética')


class AntecedentesEsteticosTests(PruebaDeFicha):
    """HU-EST-02: los antecedentes estéticos, en la misma ficha y con las casillas del papel."""

    def test_si_y_no_se_guardan_y_sin_marcar_queda_sin_responder(self):
        self.guardar(cirugia='True', cirugia_cuales='Rinoplastia', cirugia_donde='Hospital X',
                     cirugia_doctor='Dr. Y', depilacion='False')
        ficha = FichaEstetica.objects.get()
        self.assertIs(ficha.cirugia, True)
        self.assertIs(ficha.depilacion, False)
        self.assertIsNone(ficha.tratamiento_estetico)
        self.assertIsNone(ficha.moldeamiento_corporal)
        self.assertEqual((ficha.cirugia_cuales, ficha.cirugia_donde, ficha.cirugia_doctor),
                         ('Rinoplastia', 'Hospital X', 'Dr. Y'))

    def test_desmarcar_vuelve_a_sin_responder(self):
        self.guardar(cirugia='True')
        self.guardar()
        self.assertIsNone(FichaEstetica.objects.get().cirugia)

    def test_las_casillas_se_marcan_y_se_desmarcan(self):
        self.guardar(botox='on', hilos='on', depilacion_laser='on', otros_procedimientos='Mesoterapia')
        ficha = FichaEstetica.objects.get()
        self.assertTrue(ficha.botox and ficha.hilos and ficha.depilacion_laser)
        self.assertFalse(ficha.rellenos or ficha.prp or ficha.laser or ficha.depilacion_ipl)
        self.assertEqual(ficha.otros_procedimientos, 'Mesoterapia')
        self.guardar(hilos='on')
        ficha.refresh_from_db()
        self.assertFalse(ficha.botox)
        self.assertTrue(ficha.hilos)

    def test_el_resultado_de_la_depilacion_es_bueno_medio_o_malo(self):
        self.guardar(depilacion='True', depilacion_resultado='medio')
        self.assertEqual(FichaEstetica.objects.get().depilacion_resultado, 'medio')
        self.assertEqual(self.guardar(depilacion_resultado='excelente').status_code, 400)
        self.assertEqual(FichaEstetica.objects.get().depilacion_resultado, 'medio')

    def test_al_recargar_se_ve_lo_marcado(self):
        self.guardar(tratamiento_estetico='False', cirugia='True', depilacion_resultado='bueno',
                     botox='on', productos_en_casa='Protector solar')
        respuesta = self.client.get(self.url)
        contenido = respuesta.content.decode()
        self.assertRegex(contenido, r'value="False"[^>]*id="id_tratamiento_estetico_1" checked')
        self.assertRegex(contenido, r'value="True"[^>]*id="id_cirugia_0" checked')
        self.assertNotRegex(contenido, r'id="id_moldeamiento_corporal_\d" checked')
        self.assertRegex(contenido, r'value="bueno"[^>]*checked')
        self.assertRegex(contenido, r'name="botox"[^>]*checked')
        self.assertContains(respuesta, 'Protector solar')

    def test_todo_puede_quedar_vacio(self):
        self.guardar(ocupacion='Contadora')
        ficha = FichaEstetica.objects.get()
        self.assertIsNone(ficha.tratamiento_estetico)
        self.assertIsNone(ficha.cirugia)
        self.assertFalse(ficha.botox)
        self.assertEqual((ficha.depilacion_resultado, ficha.productos_en_casa), ('', ''))

    # --- Antecedentes médicos, hoja 2 del papel ---

    def test_los_antecedentes_medicos_se_guardan_en_la_ficha(self):
        self.guardar(alergico='True', alergico_a_que='Penicilina', enfermedad='False',
                     embarazos='2', partos='2', fur='2026-10-01', ciclo_regular='True',
                     fuma='on', dieta='Baja en azúcar', pastillas_para_dormir='No usa')
        ficha = FichaEstetica.objects.get()
        self.assertIs(ficha.alergico, True)
        self.assertEqual(ficha.alergico_a_que, 'Penicilina')
        self.assertIs(ficha.enfermedad, False)
        self.assertIsNone(ficha.fracturas)
        self.assertEqual((ficha.embarazos, ficha.partos, ficha.abortos), (2, 2, None))
        self.assertEqual(str(ficha.fur), '2026-10-01')
        self.assertTrue(ficha.fuma)
        self.assertFalse(ficha.alcohol)

    def test_los_numeros_no_aceptan_negativos(self):
        self.assertEqual(self.guardar(embarazos='-1').status_code, 400)
        self.assertFalse(FichaEstetica.objects.exists())

    def test_no_usa_los_antecedentes_de_prosalud(self):
        """Las clínicas son independientes: en Estética no aparece la pantalla general."""
        respuesta = self.client.get(reverse('pacientes:ver_expediente', args=[self.expediente.pk]))
        self.assertNotContains(respuesta, reverse('consultas:antecedentes', args=[self.expediente.pk]))
        self.assertNotContains(respuesta, 'Aún no se registran antecedentes')


class AtencionEsteticaTests(PruebaDeFicha):
    """HU-EST-03: cada visita de la paciente, propia de la clínica estética."""

    def setUp(self):
        super().setUp()
        self.client.post(reverse('estetica:nueva_atencion', args=[self.expediente.pk]))
        self.atencion = AtencionEstetica.objects.get()

    def url_de(self, nombre, *args):
        return reverse(f'estetica:{nombre}', args=[self.atencion.pk, *args])

    def guardar_atencion(self, **datos):
        return self.client.post(self.url_de('guardar_atencion'), datos, **self.AJAX)

    def agregar(self, nombre='Hilos tensores'):
        return self.client.post(self.url_de('agregar_procedimiento'), {'nombre': nombre}, **self.AJAX)

    def marcar(self, procedimiento):
        return self.client.post(self.url_de('marcar_sesion', procedimiento.pk), **self.AJAX)

    def finalizar(self):
        return self.client.post(self.url_de('finalizar_atencion'))

    # --- Abrir ---

    def test_nueva_atencion_queda_de_la_doctora_y_abierta(self):
        self.assertEqual(self.atencion.doctor, self.doctora)
        self.assertEqual(self.atencion.doctor_nombre, 'Elsa Miranda')
        self.assertFalse(self.atencion.cerrada)
        respuesta = self.client.get(self.url_de('atencion'))
        self.assertContains(respuesta, 'En atención')
        self.assertContains(respuesta, 'Finalizar atención')

    def test_con_una_abierta_se_retoma_esa(self):
        respuesta = self.client.post(reverse('estetica:nueva_atencion', args=[self.expediente.pk]))
        self.assertRedirects(respuesta, self.url_de('atencion'), fetch_redirect_response=False)
        self.assertEqual(AtencionEstetica.objects.count(), 1)

    def test_una_paciente_a_la_vez_en_la_estetica(self):
        otra = Expediente.objects.create(
            persona=Persona.objects.create(nombres='Otra', apellidos='Paciente'), clinica=self.estetica)
        self.client.post(reverse('estetica:nueva_atencion', args=[otra.pk]))
        self.assertFalse(AtencionEstetica.objects.filter(expediente=otra).exists())

    def test_una_consulta_abierta_en_prosalud_no_la_bloquea(self):
        """Las clínicas son independientes."""
        from consultas.models import Consulta
        medico = Expediente.objects.create(persona=self.persona, clinica=self.prosalud)
        Consulta.objects.create(expediente=medico, doctor=self.doctora, motivo='', inicio=timezone.now())
        otra = Expediente.objects.create(
            persona=Persona.objects.create(nombres='Otra', apellidos='Paciente'), clinica=self.estetica)
        self.finalizar()
        self.client.post(reverse('estetica:nueva_atencion', args=[otra.pk]))
        self.assertTrue(AtencionEstetica.objects.filter(expediente=otra).exists())

    def test_un_expediente_de_prosalud_no_tiene_atenciones(self):
        medico = Expediente.objects.create(persona=self.persona, clinica=self.prosalud)
        self.trabajar_en(self.prosalud)
        respuesta = self.client.post(reverse('estetica:nueva_atencion', args=[medico.pk]))
        self.assertEqual(respuesta.status_code, 404)

    # --- Escribir ---

    def test_el_preguardado_guarda_signos_plan_rp_y_descripcion(self):
        respuesta = self.guardar_atencion(motivo='Manchas en el rostro', presion_arterial='120/80',
                                          frecuencia_cardiaca='72', peso='60.5', talla='1.62',
                                          plan='Peeling químico', rp='Protector solar FPS 50',
                                          descripcion_tratamiento='Se aplicó la primera capa.')
        self.assertEqual(respuesta.status_code, 200)
        self.atencion.refresh_from_db()
        self.assertEqual(self.atencion.presion_arterial, '120/80')
        self.assertEqual(self.atencion.frecuencia_cardiaca, 72)
        self.assertEqual(str(self.atencion.talla), '1.62')
        self.assertEqual(self.atencion.rp, 'Protector solar FPS 50')
        self.assertEqual(self.atencion.descripcion_tratamiento, 'Se aplicó la primera capa.')

    def test_al_recargar_se_ve_lo_guardado(self):
        self.guardar_atencion(plan='Peeling químico', descripcion_tratamiento='Primera capa')
        respuesta = self.client.get(self.url_de('atencion'))
        self.assertContains(respuesta, 'Peeling químico')
        self.assertContains(respuesta, 'Primera capa')

    def test_un_signo_fuera_de_rango_no_se_guarda_y_dice_cual(self):
        respuesta = self.guardar_atencion(presion_arterial='300/80', plan='Algo')
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('P/A', respuesta.json()['mensaje'])
        self.atencion.refresh_from_db()
        self.assertEqual(self.atencion.plan, '')

    def test_otro_doctor_no_escribe_en_la_atencion(self):
        colega = Usuario.objects.create_user(username='colega', password='x', debe_cambiar_password=False)
        colega.user_permissions.add(Permission.objects.get(codename='view_expediente'))
        colega.clinicas.add(self.estetica)
        self.client.force_login(colega)
        self.trabajar_en(self.estetica)
        self.assertEqual(self.guardar_atencion(plan='Ajeno').status_code, 403)

    # --- Zonas a tratar ---

    def test_las_marcas_y_la_figura_se_guardan(self):
        marcas = [{'x': 25.5, 'y': 40, 'nota': 'Hilos'}, {'x': 70, 'y': 30.25, 'nota': ''}]
        self.assertEqual(self.guardar_atencion(figura='hombre', marcas=json.dumps(marcas)).status_code, 200)
        self.atencion.refresh_from_db()
        self.assertEqual(self.atencion.figura, 'hombre')
        self.assertEqual(self.atencion.marcas, [{'x': 25.5, 'y': 40.0, 'nota': 'Hilos', 'vectores': []},
                                                {'x': 70.0, 'y': 30.25, 'nota': '', 'vectores': []}])

    def test_las_flechas_salen_de_un_punto(self):
        marcas = [{'x': 30, 'y': 40, 'nota': 'Hilos', 'vectores': [{'x': 35, 'y': 30}, {'x': 38, 'y': 45}]}]
        self.assertEqual(self.guardar_atencion(marcas=json.dumps(marcas)).status_code, 200)
        self.atencion.refresh_from_db()
        self.assertEqual(self.atencion.marcas[0]['vectores'], [{'x': 35.0, 'y': 30.0}, {'x': 38.0, 'y': 45.0}])

    def test_una_flecha_fuera_de_la_figura_no_se_guarda(self):
        marcas = [{'x': 30, 'y': 40, 'vectores': [{'x': 130, 'y': 30}]}]
        self.assertEqual(self.guardar_atencion(marcas=json.dumps(marcas)).status_code, 400)
        self.atencion.refresh_from_db()
        self.assertEqual(self.atencion.marcas, [])

    def test_al_recargar_vuelven_las_marcas(self):
        self.guardar_atencion(marcas=json.dumps([{'x': 10, 'y': 20, 'nota': 'Frente'}]))
        respuesta = self.client.get(self.url_de('atencion'))
        self.assertContains(respuesta, 'Frente')
        self.assertContains(respuesta, 'name="marcas"')

    def test_una_marca_fuera_de_la_figura_no_se_guarda(self):
        respuesta = self.guardar_atencion(marcas=json.dumps([{'x': 150, 'y': 20}]))
        self.assertEqual(respuesta.status_code, 400)
        self.atencion.refresh_from_db()
        self.assertEqual(self.atencion.marcas, [])

    def test_la_figura_sale_del_sexo_de_la_paciente(self):
        self.persona.sexo = 'M'
        self.persona.save()
        respuesta = self.client.get(self.url_de('atencion'))
        self.assertRegex(respuesta.content.decode(), r'value="hombre"[^>]*checked')
        self.assertContains(respuesta, 'figura_hombre.webp')

    # --- Finalizar ---

    def test_finalizada_queda_de_solo_lectura(self):
        self.guardar_atencion(plan='Peeling')
        self.assertRedirects(self.finalizar(), reverse('pacientes:ver_expediente', args=[self.expediente.pk]),
                             fetch_redirect_response=False)
        self.atencion.refresh_from_db()
        self.assertTrue(self.atencion.cerrada)
        self.assertEqual(self.guardar_atencion(plan='Cambio').status_code, 409)
        self.atencion.refresh_from_db()
        self.assertEqual(self.atencion.plan, 'Peeling')
        respuesta = self.client.get(self.url_de('atencion'))
        self.assertContains(respuesta, 'Finalizada')
        self.assertNotContains(respuesta, 'Finalizar atención')
        self.assertContains(respuesta, 'disabled')

    def test_el_historial_muestra_las_atenciones(self):
        self.guardar_atencion(motivo='Manchas en el rostro')
        respuesta = self.client.get(reverse('estetica:atenciones', args=[self.expediente.pk]))
        self.assertContains(respuesta, 'Manchas en el rostro')
        self.assertContains(respuesta, self.url_de('atencion'))

    # --- Procedimientos y sesiones ---

    def test_agregar_procedimiento_devuelve_la_tabla(self):
        respuesta = self.agregar('Hilos tensores')
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('Hilos tensores', respuesta.json()['html'])
        self.assertEqual(ProcedimientoEstetico.objects.get().expediente, self.expediente)

    def test_un_procedimiento_sin_nombre_no_se_agrega(self):
        self.assertEqual(self.agregar('   ').status_code, 400)
        self.assertFalse(ProcedimientoEstetico.objects.exists())

    def test_se_marca_una_sesion_por_atencion(self):
        self.agregar()
        procedimiento = ProcedimientoEstetico.objects.get()
        self.assertEqual(self.marcar(procedimiento).status_code, 200)
        self.assertEqual(self.marcar(procedimiento).status_code, 400)
        sesion = SesionProcedimiento.objects.get()
        self.assertEqual((sesion.numero, sesion.atencion), (1, self.atencion))

    def test_la_siguiente_atencion_marca_la_sesion_dos(self):
        self.agregar()
        procedimiento = ProcedimientoEstetico.objects.get()
        self.marcar(procedimiento)
        self.finalizar()
        self.client.post(reverse('estetica:nueva_atencion', args=[self.expediente.pk]))
        self.atencion = AtencionEstetica.objects.get(cierre__isnull=True)
        self.marcar(procedimiento)
        self.assertEqual(list(procedimiento.sesiones.values_list('numero', flat=True)), [1, 2])

    def test_un_renglon_sin_marcar_en_una_visita_sigue_su_propia_cuenta(self):
        """Dos procedimientos; en la segunda visita solo se marca uno: el otro no queda con huecos."""
        self.agregar('Peeling')
        self.agregar('Hilos')
        peeling, hilos = ProcedimientoEstetico.objects.order_by('pk')
        self.marcar(peeling)
        self.marcar(hilos)
        for marcar_hilos in (False, True):
            self.finalizar()
            self.client.post(reverse('estetica:nueva_atencion', args=[self.expediente.pk]))
            self.atencion = AtencionEstetica.objects.get(cierre__isnull=True)
            self.marcar(peeling)
            if marcar_hilos:
                self.assertEqual(self.marcar(hilos).status_code, 200)
        self.assertEqual(list(peeling.sesiones.values_list('numero', flat=True)), [1, 2, 3])
        self.assertEqual(list(hilos.sesiones.values_list('numero', flat=True)), [1, 2])

    def test_no_pasa_de_diez_sesiones(self):
        self.agregar()
        procedimiento = ProcedimientoEstetico.objects.get()
        for numero in range(1, 11):
            otra = AtencionEstetica.objects.create(expediente=self.expediente, doctor=self.doctora,
                                                   cierre=timezone.now())
            SesionProcedimiento.objects.create(procedimiento=procedimiento, numero=numero, atencion=otra)
        self.assertEqual(self.marcar(procedimiento).status_code, 400)
        self.assertEqual(procedimiento.sesiones.count(), 10)

    def test_quitar_la_sesion_marcada_por_error(self):
        self.agregar()
        procedimiento = ProcedimientoEstetico.objects.get()
        self.marcar(procedimiento)
        sesion = SesionProcedimiento.objects.get()
        respuesta = self.client.post(self.url_de('quitar_sesion', sesion.pk), **self.AJAX)
        self.assertEqual(respuesta.status_code, 200)
        sesion.refresh_from_db()
        self.assertFalse(sesion.activo)
        # Se puede volver a marcar la misma sesion.
        self.assertEqual(self.marcar(procedimiento).status_code, 200)

    def test_finalizada_no_se_tocan_los_procedimientos(self):
        self.agregar()
        procedimiento = ProcedimientoEstetico.objects.get()
        self.finalizar()
        self.assertEqual(self.marcar(procedimiento).status_code, 400)
        self.assertEqual(self.agregar('Otro').status_code, 400)
        self.assertFalse(SesionProcedimiento.objects.exists())

    # --- El expediente de Estetica ya no muestra lo de ProSalud ---

    def test_el_expediente_ofrece_nueva_atencion_y_no_lo_de_prosalud(self):
        respuesta = self.client.get(reverse('pacientes:ver_expediente', args=[self.expediente.pk]))
        self.assertContains(respuesta, 'Nueva atención')
        self.assertContains(respuesta, reverse('estetica:atenciones', args=[self.expediente.pk]))
        self.assertNotContains(respuesta, 'Registrar consulta')
        self.assertNotContains(respuesta, 'Historial clínico')
        self.assertNotContains(respuesta, 'Recetas')
        self.assertNotContains(respuesta, 'CONTROLES PENDIENTES')
        self.assertContains(respuesta, 'Adjuntos')


class PdfAtencionTests(PruebaDeFicha):
    """HU-EST-03: la atención en PDF, con la figura y sus marcas."""

    def setUp(self):
        super().setUp()
        self.atencion = AtencionEstetica.objects.create(
            expediente=self.expediente, doctor=self.doctora, doctor_nombre='Elsa Miranda',
            motivo='Flacidez', figura='mujer',
            marcas=[{'x': 17, 'y': 52, 'nota': 'Hilos', 'vectores': [{'x': 12, 'y': 40}]}])
        self.url = reverse('estetica:pdf_atencion', args=[self.atencion.pk])

    def test_se_abre_en_el_visor(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'application/pdf')
        self.assertTrue(respuesta.content.startswith(b'%PDF'))
        self.assertTrue(respuesta['Content-Disposition'].startswith('inline'))
        self.assertEqual(respuesta['X-Frame-Options'], 'SAMEORIGIN')
        self.assertEqual(respuesta['X-Content-Type-Options'], 'nosniff')

    def test_con_descargar_se_baja(self):
        self.assertTrue(self.client.get(self.url + '?descargar=1')['Content-Disposition'].startswith('attachment'))

    def test_sin_marcas_tambien_sale(self):
        self.atencion.marcas = []
        self.atencion.save()
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_quien_no_es_de_la_clinica_no_lo_ve(self):
        ajena = Usuario.objects.create_user(username='ajena', password='x', debe_cambiar_password=False)
        ajena.user_permissions.add(Permission.objects.get(codename='view_expediente'))
        ajena.clinicas.add(self.prosalud)
        self.client.force_login(ajena)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_la_atencion_ofrece_el_pdf(self):
        respuesta = self.client.get(reverse('estetica:atencion', args=[self.atencion.pk]))
        self.assertContains(respuesta, f'data-ver-pdf="{self.url}"')


class PlantillaAtencionTests(PruebaDeFicha):
    """HU-EST-04: la atención estética en blanco, de mujer y de hombre."""

    def test_las_dos_figuras_salen_en_pdf(self):
        for figura in ('mujer', 'hombre'):
            with self.subTest(figura):
                respuesta = self.client.get(reverse('estetica:plantilla_atencion', args=[figura]))
                self.assertEqual(respuesta.status_code, 200)
                self.assertTrue(respuesta.content.startswith(b'%PDF'))
                self.assertTrue(respuesta['Content-Disposition'].startswith('inline'))

    def test_una_figura_desconocida_da_404(self):
        self.assertEqual(self.client.get(reverse('estetica:plantilla_atencion', args=['otra'])).status_code, 404)

    def test_no_crea_ningun_registro(self):
        self.client.get(reverse('estetica:plantilla_atencion', args=['mujer']))
        self.assertFalse(AtencionEstetica.objects.exists())

    def test_con_prosalud_activa_no_existe(self):
        self.trabajar_en(self.prosalud)
        self.assertEqual(self.client.get(reverse('estetica:plantilla_atencion', args=['mujer'])).status_code, 404)

    def test_la_pantalla_de_plantillas_ofrece_solo_las_de_estetica(self):
        respuesta = self.client.get(reverse('consultas:plantillas'))
        self.assertContains(respuesta, reverse('estetica:plantilla_atencion', args=['mujer']))
        self.assertContains(respuesta, reverse('estetica:plantilla_atencion', args=['hombre']))
        self.assertNotContains(respuesta, reverse('consultas:plantilla_pdf', args=['receta']))
