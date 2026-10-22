"""Regreso a pantallas internas de lectura, conservando busquedas y paginacion."""
from urllib.parse import urlsplit

from django.urls import Resolver404, resolve, reverse
from django.utils.http import url_has_allowed_host_and_scheme


def url_interna_segura(request, valor, vistas):
    if not valor or len(valor) > 4096 or not url_has_allowed_host_and_scheme(
            valor, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return None
    partes = urlsplit(valor)
    try:
        if resolve(partes.path).view_name not in vistas:
            return None
    except Resolver404:
        return None
    return partes.path + ('?' + partes.query if partes.query else '')


ORIGENES_EXPEDIENTE = {
    'core:home', 'pacientes:lista_pacientes', 'pacientes:cola_consultas',
    'pacientes:ver_expediente', 'consultas:atender_consulta', 'consultas:ver_consulta',
    'consultas:historial_consultas', 'consultas:antecedentes', 'consultas:adjuntos',
    'consultas:lista_documentos', 'consultas:lista_recetas', 'consultas:lista_ordenes',
    'consultas:lista_aplicaciones', 'consultas:lista_controles',
}


def regreso_expediente(request, expediente):
    origenes = request.session.get('origenes_expediente', {})
    clave = str(expediente.pk)
    propio = reverse('pacientes:ver_expediente', args=[expediente.pk])
    origen = (url_interna_segura(request, request.GET.get('volver'), ORIGENES_EXPEDIENTE)
              or url_interna_segura(request, request.META.get('HTTP_REFERER'), ORIGENES_EXPEDIENTE))
    if origen and urlsplit(origen).path != propio:
        # Volver desde el expediente no es una nueva entrada a la consulta.
        # Asi no se cambia su regreso original (p. ej. la cola) por el expediente.
        if resolve(urlsplit(origen).path).view_name in {'consultas:atender_consulta', 'consultas:ver_consulta'}:
            origen += ('&' if '?' in origen else '?') + 'mantener_origen=1'
        origenes = {**origenes, clave: origen}
        if len(origenes) > 20:
            del origenes[next(iter(origenes))]
        request.session['origenes_expediente'] = origenes
    return (url_interna_segura(request, origenes.get(clave), ORIGENES_EXPEDIENTE)
            or reverse('pacientes:lista_pacientes'))
