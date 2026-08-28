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

    class Meta:
        verbose_name = 'usuario'
        verbose_name_plural = 'usuarios'
