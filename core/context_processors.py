from .clinica_activa import clinica_activa as obtener_clinica_activa


def clinica_activa(request):
    """Clinica activa y, si pertenece a varias, la lista para el selector del menu."""
    clinica = obtener_clinica_activa(request)
    clinicas = getattr(request, '_clinicas_del_usuario', [])
    return {
        'clinica_activa': clinica,
        'clinicas_para_elegir': clinicas if len(clinicas) > 1 else [],
    }
