"""
Registro de acciones sensibles en la bitácora de auditoría.

Se llama explícitamente desde la vista que hace la acción, en una línea:

    from core.auditoria import registrar
    from core.models import RegistroAuditoria

    registrar(
        request,
        RegistroAuditoria.Accion.RESETEAR_PASSWORD,
        objetivo=usuario.username,
    )

Es explícito a propósito: así se ve en la vista qué queda auditado, en vez
de que ocurra por magia en algún lado difícil de encontrar.
"""

from .models import RegistroAuditoria


def registrar(request, accion, objetivo='', detalle=''):
    """
    Deja constancia de una acción en la bitácora.

    El nombre de quien la hizo se guarda también como texto, para que la
    bitácora no cambie si esa persona edita su perfil después.
    """
    usuario = request.user if request.user.is_authenticated else None

    return RegistroAuditoria.objects.create(
        usuario=usuario,
        usuario_nombre=usuario.username if usuario else 'sistema',
        accion=accion,
        objetivo=objetivo,
        detalle=detalle,
    )
