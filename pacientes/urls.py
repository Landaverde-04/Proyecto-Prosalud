from django.urls import path
from . import views

app_name = 'pacientes'

urlpatterns = [
    path('', views.lista_pacientes, name='lista_pacientes'),
    path('nuevo/', views.registrar_paciente, name='registrar_paciente'),
    path('buscar-persona/', views.buscar_persona, name='buscar_persona'),
    path('expediente/<int:expediente_id>/', views.ver_expediente, name='ver_expediente'),
    path('expediente/<int:expediente_id>/agregar-contacto/', views.agregar_contacto, name='agregar_contacto'),
    path(
        'expediente/<int:expediente_id>/contacto/<int:contacto_id>/editar/',
        views.editar_contacto, name='editar_contacto',
    ),
    path(
        'expediente/<int:expediente_id>/contacto/<int:contacto_id>/desactivar/',
        views.desactivar_contacto, name='desactivar_contacto',
    ),
    path(
        'expediente/<int:expediente_id>/preconsulta/',
        views.registrar_preconsulta, name='registrar_preconsulta',
    ),
]
