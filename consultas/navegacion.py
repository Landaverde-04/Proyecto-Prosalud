"""Origen de una visita a la consulta; no depende de history.back()."""
from django.urls import reverse
from core.navegacion import url_interna_segura


ORIGENES = {'core:home', 'pacientes:cola_consultas', 'pacientes:lista_pacientes',
            'pacientes:ver_expediente', 'consultas:historial_consultas'}


def origen_seguro(request, valor):
    return url_interna_segura(request, valor, ORIGENES)


def regreso_consulta(request, consulta, recordar=True):
    origenes = request.session.get('origenes_consulta', {})
    clave = str(consulta.pk)
    if recordar and request.GET.get('mantener_origen') != '1':
        origen = (origen_seguro(request, request.POST.get('volver') or request.GET.get('volver'))
                  or origen_seguro(request, request.META.get('HTTP_REFERER')))
        if origen:
            origenes = {**origenes, clave: origen}
            if len(origenes) > 20:
                del origenes[next(iter(origenes))]
            request.session['origenes_consulta'] = origenes
    return (origen_seguro(request, origenes.get(clave))
            or (reverse('pacientes:cola_consultas') if consulta.expediente.clinica.usa_cola
                else reverse('consultas:historial_consultas', args=[consulta.expediente_id])))
