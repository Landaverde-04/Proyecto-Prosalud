from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from pacientes.inicio import resumen_de_atencion

from .clinica_activa import cambiar_clinica_activa, clinica_activa, clinicas_del_usuario
from .models import RegistroAuditoria
from .paginacion import paginar, es_ajax


def _accesos_rapidos(usuario, clinica):
    """Accesos del inicio agrupados por seccion; solo los que el permiso del usuario y la clinica abren."""
    atiende = usuario.has_perm('consultas.change_consulta') and not usuario.has_perm('auth.change_group')
    # La cola solo existe en la clinica que la usa; en la que atiende por cita no hay acceso.
    permiso_cola = 'consultas.view_consulta' if clinica and clinica.usa_cola else False
    secciones = [
        ('Atención', [
            ('pacientes.add_persona', 'Nuevo paciente', 'Adulto o menor, con su contacto',
             'bi-person-plus', reverse('pacientes:registrar_paciente')),
            ('pacientes.view_persona', 'Buscar paciente', 'Por nombre, DUI o teléfono',
             'bi-search', reverse('pacientes:lista_pacientes')),
            (permiso_cola, 'Cola de consulta',
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
            # None: sin permiso requerido; False: no aplica a esta clinica.
            if permiso is None or (permiso and usuario.has_perm(permiso))
        ]
        if visibles:
            resultado.append({'titulo': titulo, 'accesos': visibles})
    return resultado


@login_required
def home(request):
    usuario = request.user
    clinica = clinica_activa(request)
    resumen = resumen_de_atencion(usuario, clinica)
    accesos = _accesos_rapidos(usuario, clinica)
    return render(request, 'core/home.html', {
        'rol': usuario.groups.first(),
        'accesos': accesos,
        # Solo "Mi cuenta": el puesto todavia no tiene pantallas propias.
        'sin_pantallas': all(seccion['titulo'] == 'Mi cuenta' for seccion in accesos),
        'resumen': resumen,
        # Columna derecha solo si hay algun panel: medico (proximos) o enfermeria (colas).
        'hay_paneles': bool(resumen) and (resumen['proximos'] is not None or resumen['colas'] is not None),
    })


@require_POST
@login_required
def cambiar_clinica(request):
    """
    Cambia la clinica activa entre las del propio usuario. No exige un permiso
    aparte: solo elige entre clinicas que ya tiene asignadas.
    """
    clinica_id = request.POST.get('clinica', '')
    clinica = clinicas_del_usuario(request.user).filter(pk=clinica_id).first() if clinica_id.isdigit() else None
    if clinica is None:
        raise Http404
    cambiar_clinica_activa(request, clinica)
    messages.success(request, f'Ahora trabajas en {clinica.nombre}.')
    # Por defecto al inicio: la pantalla anterior podia ser de la otra clinica.
    # Solo se sigue 'siguiente' si es una ruta de este mismo sitio (nunca a otro dominio).
    siguiente = request.POST.get('siguiente', '')
    if siguiente and url_has_allowed_host_and_scheme(
        siguiente, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        return redirect(siguiente)
    return redirect('core:home')


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
