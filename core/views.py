from django.shortcuts import render
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q

from .models import RegistroAuditoria
from .paginacion import paginar, es_ajax


@login_required
def home(request):
    return render(request, 'core/home.html')


@login_required
@permission_required('core.view_registroauditoria', raise_exception=True)
def bitacora(request):
    """
    Bitácora de acciones sensibles.

    El filtro y la paginación viajan en la URL (?q=, ?desde=, ?hasta= y
    ?page=) en vez de resolverse en el navegador. Es el patrón que
    necesitan los listados que crecen sin límite -- la búsqueda de
    pacientes de HU-23 debería seguir este mismo camino.
    """
    registros = RegistroAuditoria.objects.select_related('usuario')

    consulta = request.GET.get('q', '').strip()
    if consulta:
        registros = registros.filter(
            Q(usuario_nombre__icontains=consulta)
            | Q(objetivo__icontains=consulta)
            | Q(detalle__icontains=consulta)
        )

    accion = request.GET.get('accion', '').strip()
    if accion:
        registros = registros.filter(accion=accion)

    desde = request.GET.get('desde', '').strip()
    if desde:
        registros = registros.filter(fecha__date__gte=desde)

    hasta = request.GET.get('hasta', '').strip()
    if hasta:
        registros = registros.filter(fecha__date__lte=hasta)

    total = registros.count()
    pagina = paginar(registros, request)

    contexto = {
        'pagina': pagina,
        'consulta': consulta,
        'accion_activa': accion,
        'desde': desde,
        'hasta': hasta,
        'acciones': RegistroAuditoria.Accion.choices,
        'total': total,
    }
    plantilla = 'core/resultados_bitacora.html' if es_ajax(request) else 'core/bitacora.html'
    return render(request, plantilla, contexto)
