"""
Clinica en la que trabaja el usuario durante su sesion.

Quien pertenece a una sola clinica trabaja siempre en ella. Quien pertenece
a varias la elige con el selector del menu; se guarda en la sesion y en
Usuario.ultima_clinica para retomarla en el siguiente inicio de sesion.

    from core.clinica_activa import clinica_activa

    clinica = clinica_activa(request)
"""

CLAVE_SESION = 'clinica_activa_id'
# Campo oculto que cada formulario lleva con la clinica con la que se dibujo.
CAMPO_FORMULARIO = 'clinica_formulario'


def clinicas_del_usuario(usuario):
    """Clinicas activas a las que pertenece, en orden de creacion."""
    return usuario.clinicas.filter(activo=True).order_by('pk')


def clinica_activa(request):
    """La clinica activa del usuario, validada en cada peticion. None si no tiene ninguna."""
    if not request.user.is_authenticated:
        return None
    # Una sola consulta por peticion, aunque la pidan la vista y el context processor.
    if hasattr(request, '_clinica_activa'):
        return request._clinica_activa

    clinicas = list(clinicas_del_usuario(request.user))
    por_id = {clinica.pk: clinica for clinica in clinicas}
    # Si le quitaron la clinica guardada, deja de valer y se toma otra.
    clinica = (
        por_id.get(request.session.get(CLAVE_SESION))
        or por_id.get(request.user.ultima_clinica_id)
        or (clinicas[0] if clinicas else None)
    )
    if clinica and request.session.get(CLAVE_SESION) != clinica.pk:
        request.session[CLAVE_SESION] = clinica.pk

    request._clinica_activa = clinica
    request._clinicas_del_usuario = clinicas
    return clinica


def formulario_de_otra_clinica(request, clinica):
    """
    El formulario se dibujo con otra clinica: la sesion es una sola, asi que
    cambiarla en una pestaña deja a las demas mostrando datos de la anterior.
    Se incluye el campo con el parcial core/campo_clinica.html.
    """
    enviada = request.POST.get(CAMPO_FORMULARIO, '')
    return bool(enviada) and clinica is not None and enviada != str(clinica.pk)


def cambiar_clinica_activa(request, clinica):
    """Fija la clinica elegida en la sesion y la recuerda para el siguiente inicio de sesion."""
    request.session[CLAVE_SESION] = clinica.pk
    request._clinica_activa = clinica
    if request.user.ultima_clinica_id != clinica.pk:
        request.user.ultima_clinica = clinica
        request.user.save(update_fields=['ultima_clinica'])
