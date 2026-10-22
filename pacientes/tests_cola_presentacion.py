"""HU-EXP-13: regresiones del fragmento de cola, sin consultar la base.

Estas pruebas protegen el marcado y los permisos de los botones. El ajuste
de anchos y los saltos de linea se comprueban adicionalmente en navegador.
"""
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.utils import timezone


class ColaPresentacionTests(SimpleTestCase):
    def setUp(self):
        persona = SimpleNamespace(
            nombres='María Alejandra Guadalupe de los Ángeles',
            apellidos='Hernández de la Cruz Montenegro',
        )
        self.nombre = f'{persona.nombres} {persona.apellidos}'
        medico = SimpleNamespace(
            pk=1, username='medico_qa',
            get_full_name='Doctora María Alejandra Hernández de la Cruz Montenegro',
        )
        self.consulta = SimpleNamespace(
            pk=10, expediente=SimpleNamespace(persona=persona),
            inicio=timezone.now(), hora_llegada=timezone.now(),
            es_emergencia=False, tiene_preconsulta=True, doctor_id=1,
            reasignaciones=SimpleNamespace(all=[]),
        )
        self.contexto = {
            'colas': [{'medico': medico, 'consultas': [self.consulta],
                       'en_atencion': [self.consulta]}],
            'user': SimpleNamespace(pk=1),
            'puede_atender': True,
            'puede_gestionar': True,
            'puede_editar_preconsulta': True,
        }

    def renderizar(self, solo_la_suya, **extra):
        contexto = {**self.contexto, 'solo_la_suya': solo_la_suya, **extra}
        return render_to_string('pacientes/resultados_cola.html', contexto)

    def test_nombres_completos_sin_clase_de_truncamiento_en_ambas_vistas(self):
        for solo_la_suya in (True, False):
            with self.subTest(solo_la_suya=solo_la_suya):
                html = self.renderizar(solo_la_suya)
                self.assertIn(self.nombre, html)
                self.assertIn('cola-nombre', html)
                self.assertIn('cola-identidad', html)
                self.assertNotIn('text-truncate', html)

    def test_el_nombre_del_medico_tambien_puede_ocupar_varias_lineas(self):
        html = self.renderizar(False)
        self.assertIn('cola-medico', html)
        self.assertIn(self.contexto['colas'][0]['medico'].get_full_name, html)

    def test_atender_bloqueado_conserva_el_aviso_y_no_envia_la_consulta(self):
        html = self.renderizar(True)
        self.assertIn('cola-accion-siguiente', html)
        self.assertIn('cola-boton-atender', html)
        self.assertIn('aria-describedby="cola-bloqueo-10"', html)
        self.assertIn('id="cola-bloqueo-10"', html)
        self.assertIn('Finalice la consulta en atención primero', html)
        self.assertNotIn('type="submit"', html)
        self.assertNotIn('btn-lg', html)

    def test_atender_habilitado_usa_el_mismo_bloque_en_emergencia_o_sin_consulta_activa(self):
        for emergencia in (False, True):
            with self.subTest(emergencia=emergencia):
                self.consulta.es_emergencia = emergencia
                cola = {**self.contexto['colas'][0],
                        'en_atencion': [self.consulta] if emergencia else []}
                html = self.renderizar(True, colas=[cola])
                self.assertIn('cola-accion-siguiente', html)
                self.assertIn('cola-boton-atender', html)
                self.assertIn('type="submit"', html)
                self.assertNotIn('cola-bloqueo-', html)
                self.assertNotIn('btn-lg', html)

    def test_la_presentacion_no_agrega_acciones_sin_permiso(self):
        for solo_la_suya in (True, False):
            with self.subTest(solo_la_suya=solo_la_suya):
                html = self.renderizar(
                    solo_la_suya, puede_atender=False, puede_gestionar=False,
                    puede_editar_preconsulta=False,
                )
                self.assertIn(self.nombre, html)
                self.assertNotIn('>Atender</button>', html)
                self.assertNotIn('Continuar</a>', html)
                self.assertNotIn('data-abrir-modal=', html)
                self.assertNotIn('title="Editar preconsulta"', html)

    def test_el_nombre_sigue_escapado_como_texto(self):
        self.consulta.expediente.persona.nombres = '<script>paciente</script>'
        for solo_la_suya in (True, False):
            with self.subTest(solo_la_suya=solo_la_suya):
                html = self.renderizar(solo_la_suya)
                self.assertNotIn('<script>paciente</script>', html)
                self.assertIn('&lt;script&gt;paciente&lt;/script&gt;', html)
