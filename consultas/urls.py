from django.urls import path
from . import views

app_name = 'consultas'
urlpatterns = [
    path('expediente/<int:expediente_id>/documentos/', views.lista_documentos, name='lista_documentos'),
    path('<int:consulta_id>/documentos/nuevo/', views.nuevo_documento, name='nuevo_documento'),
    path('documentos/previa/<uuid:previa_id>/', views.previsualizar_documento, name='previsualizar_documento'),
    path('documentos/previa/<uuid:previa_id>/pdf/', views.pdf_previa, name='pdf_previa'),
    path('documentos/previa/<uuid:previa_id>/emitir/', views.emitir_documento, name='emitir_documento'),
    path('documentos/<int:documento_id>/', views.ver_documento, name='ver_documento'),
    path('documentos/<int:documento_id>/pdf/', views.pdf_documento, name='pdf_documento'),
]
