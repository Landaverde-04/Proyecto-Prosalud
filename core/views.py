from django.shortcuts import render
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q
from django.urls import reverse

from pacientes.inicio import resumen_de_atencion

from .models import RegistroAuditoria
from .paginacion import paginar, es_ajax


def _accesos_rapidos(usuario):
    """Accesos del inicio agrupados por seccion; solo los que el permiso del usuario abre."""
    atiende =usuario.has_perm('consultas.change_consulta') and not usuario.has_perm('auth.change_group')
    secciones = [
        ('Atención', [
            ('pacientes.add_persona', 'Nuevo paciente', 'Adulto o menor, con su contacto',
             'bi-person-plus', reverse('pacientes:registrar_paciente')),
            ('pacientes.view_persona', 'Buscar paciente', 'Por nombre, DUI o teléfono',
             'bi-search', reverse('pacientes:lista_pacientes')),
            ('consultas.view_consulta', 'Cola de consulta',
             'Tus pacientes en espera' if atiende else 'En espera, por médico',
             'bi-list-ol', reverse('pacientes:cola_consultas')),
        ]),
        ('Administración', [
            ('seguridad.view_usuario', 'Usuarios', 'Cuentas y contraseñas',
             'bi-people', reverse('seguridad:lista_usuarios')),
            ('auth.view_group', 'Roles', 'Permisos por puesto', 'bi-shield-lock', reverse('seguridad:lista_roles')),
            ('core.view_registroauditoria', 'Bitácora', 'Quién cambió qué',
             'bi-journal-text', reverse('core:bitacora')),
        ]),
        ('Mi cuenta', [
            (None, 'Mi perfil', 'Datos y contraseña', 'bi-person-circle', reverse('seguridad:mi_perfil')),
        ]),
    ]
    resultado = []
    for titulo, accesos in secciones:
        visibles = [
            {'titulo': nombre, 'descripcion': descripcion, 'icono': icono, 'url': url}
            for permiso, nombre, descripcion, icono, url in accesos
            if permiso is None or usuario.has_perm(permiso)
        ]
        if visibles:
            resultado.append({'titulo': titulo, 'accesos': visibles})
    return resultado


@login_required
def home(request):
    usuario = request.user
    resumen = resumen_de_atencion(usuario)
    return render(request, 'core/home.html', {
        'clinicas': usuario.clinicas.all(),
        'rol': usuario.groups.first(),
        'accesos': _accesos_rapidos(usuario),
        'resumen': resumen,
        # Columna derecha solo si hay algun panel: medico (proximos) o enfermeria (colas).
        'hay_paneles': bool(resumen) and (resumen['proximos'] is not None or resumen['colas'] is not None),
    })


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
