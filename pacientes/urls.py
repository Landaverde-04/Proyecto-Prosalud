from django.urls import path
from . import views

app_name = 'pacientes'

urlpatterns = [
    path('', views.lista_pacientes, name='lista_pacientes'),
    path('nuevo-adulto/', views.registrar_adulto, name='registrar_adulto'),
    path('buscar-persona/', views.buscar_persona, name='buscar_persona'),
]
