from django.urls import path

from . import views

app_name = 'inventario'

urlpatterns = [
    path('productos/', views.lista_productos, name='lista_productos'),
    path('productos/nuevo/', views.crear_producto, name='crear_producto'),
    path('productos/<int:producto_id>/', views.detalle_producto, name='detalle_producto'),
    path('productos/<int:producto_id>/entrada/', views.registrar_entrada, name='registrar_entrada'),
    path('productos/<int:producto_id>/editar/', views.editar_producto, name='editar_producto'),
    path('productos/<int:producto_id>/cambiar-estado/', views.cambiar_estado_producto,
         name='cambiar_estado_producto'),
]
