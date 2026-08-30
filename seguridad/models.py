from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    """
    Modelo de usuario del sistema. Extiende AbstractUser de Django,
    que ya provee: username, password, email, first_name, last_name,
    is_active, date_joined, last_login, groups y permissions.

    No hereda ModeloBase porque AbstractUser ya cubre esos campos.
    """

    debe_cambiar_password = models.BooleanField(default=False)

    # JVPM (Junta de Vigilancia de la Profesion Medica): solo aplica a
    # doctores, por eso opcional -- enfermeria, laboratorio y regente lo
    # dejan en blanco. Se usa al imprimir documentos (HU-EXP-26).
    jvpm = models.CharField('JVPM', max_length=20, blank=True)

    # Muchos a muchos porque la doctora administradora trabaja en las dos
    # clinicas (Medica y Estetica) y el resto del personal solo en la
    # suya (TEC-01). Un expediente pertenece a una sola clinica, pero un
    # usuario puede tener acceso a varias.
    clinicas = models.ManyToManyField(
        'core.Clinica', related_name='usuarios', blank=True,
        db_table='UsuarioClinica',
    )

    class Meta:
        db_table = 'Usuario'
        verbose_name = 'usuario'
        verbose_name_plural = 'usuarios'
