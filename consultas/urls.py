from django.urls import path
from . import views

app_name = 'consultas'
urlpatterns = [
    # Antecedentes del paciente -- HU-EXP-07
    path('expediente/<int:expediente_id>/antecedentes/', views.antecedentes, name='antecedentes'),
    path('antecedentes/<int:antecedente_id>/desactivar/', views.desactivar_antecedente, name='desactivar_antecedente'),

    # Consulta -- HU-EXP-17/18/19
    path('expediente/<int:expediente_id>/historial/', views.historial_consultas, name='historial_consultas'),
    path('expediente/<int:expediente_id>/nueva/', views.nueva_consulta, name='nueva_consulta'),
    path('<int:consulta_id>/iniciar/', views.iniciar_consulta, name='iniciar_consulta'),
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
