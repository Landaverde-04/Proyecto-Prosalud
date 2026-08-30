from django.conf import settings
from django.db import models


class ModeloBase(models.Model):
    """
    Campos comunes a todos los modelos del sistema.

    Sobre creado_por / modificado_por: Django no conoce al usuario dentro
    del modelo (los modelos no saben nada del request), asi que estos
    campos NO se llenan solos. La convencion es que la vista los asigne:

        paciente = form.save(commit=False)
        paciente.creado_por = request.user      # solo al crear
        paciente.modificado_por = request.user  # siempre
        paciente.save()

    Se dejo explicito a proposito, en vez de resolverlo con middleware y
    variables de hilo: eso funciona pero esconde el mecanismo y es una
    fuente clasica de errores raros. Aqui se ve quien lo puso y donde.
    """

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)
    activo = models.BooleanField(default=True)

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        editable=False,
        related_name='%(app_label)s_%(class)s_creados',
        verbose_name='creado por',
    )
    modificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        editable=False,
        related_name='%(app_label)s_%(class)s_modificados',
        verbose_name='modificado por',
    )

    class Meta:
        abstract = True


class RegistroAuditoria(models.Model):
    """
    Bitacora de acciones sensibles del sistema.

    Existe porque hay acciones que NO dejan rastro en ningun registro:
    resetear una contrasena no cambia ningun campo visible, y cambiarle el
    rol a alguien tampoco. Sin esta bitacora serian invisibles, y son
    justamente las mas delicadas.

    No hereda de ModeloBase: una entrada de auditoria no se edita ni se
    desactiva nunca. Solo se crea y se lee.
    """

    class Accion(models.TextChoices):
        CREAR_USUARIO = 'crear_usuario', 'Creó un usuario'
        EDITAR_USUARIO = 'editar_usuario', 'Editó un usuario'
        ACTIVAR_USUARIO = 'activar_usuario', 'Activó un usuario'
        DESACTIVAR_USUARIO = 'desactivar_usuario', 'Desactivó un usuario'
        RESETEAR_PASSWORD = 'resetear_password', 'Restableció una contraseña'
        CAMBIAR_ROL = 'cambiar_rol', 'Cambió el rol de un usuario'
        CREAR_ROL = 'crear_rol', 'Creó un rol'
        EDITAR_ROL = 'editar_rol', 'Modificó un rol'
        ELIMINAR_ROL = 'eliminar_rol', 'Eliminó un rol'

    fecha = models.DateTimeField(auto_now_add=True, db_index=True)

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='acciones_auditadas',
        verbose_name='quién lo hizo',
    )
    # El nombre se congela al momento del hecho, igual que en los documentos
    # clinicos: si manana el usuario cambia de nombre, la bitacora debe
    # seguir diciendo como se llamaba cuando hizo la accion.
    usuario_nombre = models.CharField('nombre en ese momento', max_length=150)

    accion = models.CharField(max_length=40, choices=Accion.choices)
    objetivo = models.CharField(
        'sobre quién o qué', max_length=200, blank=True,
    )
    detalle = models.TextField(blank=True)

    class Meta:
        verbose_name = 'registro de auditoría'
        verbose_name_plural = 'registros de auditoría'
        ordering = ['-fecha']
        # La bitacora solo se consulta; no hay pantalla que cree, edite ni
        # borre entradas, asi que esos permisos no se ofrecen.
        default_permissions = ('view',)

    def __str__(self):
        return f'{self.fecha:%d/%m/%Y %H:%M} · {self.usuario_nombre} · {self.get_accion_display()}'
