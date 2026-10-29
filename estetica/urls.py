from django.urls import path

from . import views

app_name = 'estetica'

urlpatterns = [
    path('expediente/<int:expediente_id>/ficha/', views.ficha, name='ficha'),
    path('expediente/<int:expediente_id>/ficha/guardar/', views.guardar_ficha, name='guardar_ficha'),
    path('expediente/<int:expediente_id>/atenciones/', views.atenciones, name='atenciones'),
    path('expediente/<int:expediente_id>/atenciones/nueva/', views.nueva_atencion, name='nueva_atencion'),
    path('atencion/<int:atencion_id>/', views.atencion, name='atencion'),
    path('atencion/<int:atencion_id>/guardar/', views.guardar_atencion, name='guardar_atencion'),
    path('atencion/<int:atencion_id>/finalizar/', views.finalizar_atencion, name='finalizar_atencion'),
    path('atencion/<int:atencion_id>/pdf/', views.pdf_atencion, name='pdf_atencion'),
    path('plantillas/atencion/<str:figura>/', views.plantilla_atencion, name='plantilla_atencion'),
    path('atencion/<int:atencion_id>/procedimientos/', views.agregar_procedimiento, name='agregar_procedimiento'),
    path('atencion/<int:atencion_id>/procedimientos/<int:procedimiento_id>/sesion/',
         views.marcar_sesion, name='marcar_sesion'),
    path('atencion/<int:atencion_id>/sesiones/<int:sesion_id>/quitar/', views.quitar_sesion, name='quitar_sesion'),
]
