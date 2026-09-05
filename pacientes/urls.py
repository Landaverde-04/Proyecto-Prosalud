from django.urls import path
from . import views

app_name = 'pacientes'

urlpatterns = [
    path('', views.lista_pacientes, name='lista_pacientes'),
    path('nuevo/', views.registrar_paciente, name='registrar_paciente'),
    path('buscar-persona/', views.buscar_persona, name='buscar_persona'),
]
