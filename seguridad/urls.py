from django.urls import path
from . import views

app_name = 'seguridad'

urlpatterns = [
    path('login/', views.IniciarSesionView.as_view(), name='login'),
    path('logout/', views.CerrarSesionView.as_view(), name='logout'),

    # Usuarios
    path('usuarios/', views.lista_usuarios, name='lista_usuarios'),
    path('usuarios/crear/', views.crear_usuario, name='crear_usuario'),
    path('usuarios/<int:id>/', views.detalle_usuario, name='detalle_usuario'),
    path('usuarios/<int:id>/editar/', views.editar_usuario, name='editar_usuario'),
    path('usuarios/<int:id>/cambiar-estado/', views.cambiar_estado_usuario, name='cambiar_estado_usuario'),
    path('usuarios/<int:id>/resetear-password/', views.resetear_password, name='resetear_password'),

    # Roles
    path('roles/', views.lista_roles, name='lista_roles'),
    path('roles/crear/', views.crear_rol, name='crear_rol'),
    path('roles/<int:id>/editar/', views.editar_rol, name='editar_rol'),
    path('roles/<int:id>/eliminar/', views.eliminar_rol, name='eliminar_rol'),
    path('roles/<int:id>/usuarios/', views.usuarios_rol, name='usuarios_rol'),

    # Perfil propio
    path('mi-perfil/', views.mi_perfil, name='mi_perfil'),
    path('mi-perfil/cambiar-password/', views.CambiarPasswordView.as_view(), name='cambiar_password'),
]
