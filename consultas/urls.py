from django.urls import path
from . import views

app_name = 'consultas'
urlpatterns = [
    # Antecedentes del paciente -- HU-EXP-07
    path('expediente/<int:expediente_id>/antecedentes/', views.antecedentes, name='antecedentes'),
    path('antecedentes/<int:antecedente_id>/editar/', views.editar_antecedente, name='editar_antecedente'),
    path('antecedentes/<int:antecedente_id>/desactivar/', views.desactivar_antecedente, name='desactivar_antecedente'),

    # Adjuntos del expediente -- HU-EXP-08
    path('expediente/<int:expediente_id>/adjuntos/', views.adjuntos, name='adjuntos'),
    path('adjuntos/<int:adjunto_id>/archivo/', views.descargar_adjunto, name='descargar_adjunto'),
    path('adjuntos/<int:adjunto_id>/retirar/', views.retirar_adjunto, name='retirar_adjunto'),

    # Receta -- HU-EXP-25
    path('expediente/<int:expediente_id>/recetas/', views.lista_recetas, name='lista_recetas'),
    path('<int:consulta_id>/receta/', views.agregar_medicamento, name='agregar_medicamento'),
    path('receta/medicamento/<int:detalle_id>/quitar/', views.quitar_medicamento, name='quitar_medicamento'),
    path('receta/medicamento/<int:detalle_id>/editar/', views.editar_medicamento, name='editar_medicamento'),
    path('recetas/<int:receta_id>/', views.ver_receta, name='ver_receta'),
    path('recetas/<int:receta_id>/pdf/', views.pdf_receta, name='pdf_receta'),

    # Ordenes de examen -- HU-EXP-20
    path('expediente/<int:expediente_id>/examenes/', views.lista_ordenes, name='lista_ordenes'),
    path('<int:consulta_id>/examenes/', views.agregar_orden, name='agregar_orden'),
    path('examenes/<int:orden_id>/', views.ver_orden, name='ver_orden'),
    path('examenes/<int:orden_id>/pdf/', views.pdf_orden, name='pdf_orden'),

    # Aplicaciones y servicios -- HU-EXP-21
    path('expediente/<int:expediente_id>/aplicaciones/', views.lista_aplicaciones, name='lista_aplicaciones'),
    path('<int:consulta_id>/aplicacion/', views.agregar_aplicacion, name='agregar_aplicacion'),
    path('aplicaciones/<int:aplicacion_id>/aplicar/', views.marcar_aplicacion, name='marcar_aplicacion'),

    # Control posterior -- HU-EXP-24
    path('expediente/<int:expediente_id>/controles/', views.lista_controles, name='lista_controles'),
    path('<int:consulta_id>/control/', views.agregar_control, name='agregar_control'),
    path('controles/<int:control_id>/estado/', views.cambiar_estado_control, name='cambiar_estado_control'),
    path('controles/<int:control_id>/reprogramar/', views.reprogramar_control, name='reprogramar_control'),

    # Referencia medica -- HU-EXP-23
    path('expediente/<int:expediente_id>/referencias/', views.lista_referencias, name='lista_referencias'),
    path('<int:consulta_id>/referencia/', views.agregar_referencia, name='agregar_referencia'),
    path('referencias/<int:referencia_id>/', views.ver_referencia, name='ver_referencia'),
    path('referencias/<int:referencia_id>/pdf/', views.pdf_referencia, name='pdf_referencia'),

    # Consulta -- HU-EXP-17/18/19
    path('expediente/<int:expediente_id>/historial/', views.historial_consultas, name='historial_consultas'),
    path('expediente/<int:expediente_id>/nueva/', views.nueva_consulta, name='nueva_consulta'),
    path('<int:consulta_id>/iniciar/', views.iniciar_consulta, name='iniciar_consulta'),
    path('<int:consulta_id>/signos-vitales/', views.signos_vitales_consulta, name='signos_vitales_consulta'),
    path('<int:consulta_id>/atender/', views.atender_consulta, name='atender_consulta'),
    path('<int:consulta_id>/borrador/', views.guardar_borrador, name='guardar_borrador'),
    path('<int:consulta_id>/finalizar/', views.finalizar_consulta, name='finalizar_consulta'),
    path('<int:consulta_id>/incapacidad/', views.agregar_incapacidad, name='agregar_incapacidad'),
    path('<int:consulta_id>/', views.ver_consulta, name='ver_consulta'),

    # Documentos de la consulta -- HU-EXP-22
    path('expediente/<int:expediente_id>/documentos/', views.lista_documentos, name='lista_documentos'),
    path('<int:consulta_id>/documentos/nuevo/', views.nuevo_documento, name='nuevo_documento'),
    path('documentos/previa/<uuid:previa_id>/', views.previsualizar_documento, name='previsualizar_documento'),
    path('documentos/previa/<uuid:previa_id>/pdf/', views.pdf_previa, name='pdf_previa'),
    path('documentos/previa/<uuid:previa_id>/emitir/', views.emitir_documento, name='emitir_documento'),
    path('documentos/<int:documento_id>/', views.ver_documento, name='ver_documento'),
    path('documentos/<int:documento_id>/pdf/', views.pdf_documento, name='pdf_documento'),
]
