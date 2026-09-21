"""Resumen de la atencion del dia para la pantalla de inicio."""

from django.db.models import Count, Q
from django.utils import timezone

from consultas.models import Consulta

from .models import Expediente
from .views import PERMISOS_ENFERMERIA, _medicos_disponibles, _solo_su_propia_cola


def resumen_de_atencion(usuario, clinica):
    """Cifras, proximos pacientes y colas de la clinica activa. None si no aplica al usuario o a la clinica."""
    ve_cola = usuario.has_perm('consultas.view_consulta')
    ve_pacientes = usuario.has_perm('pacientes.view_persona')
    # Todo el resumen gira alrededor de la cola: una clinica que atiende por cita no lo tiene.
    if clinica is None or not clinica.usa_cola or not (ve_cola or ve_pacientes):
        return None

    clinicas = [clinica]
    hoy = timezone.localdate()
    solo_lo_suyo = _solo_su_propia_cola(usuario)
    # Atendidos y pacientes nuevos del dia son un control para quien atiende;
    # enfermeria solo necesita lo que mueve la cola.
    ve_control = usuario.has_perm('consultas.change_consulta')
    resumen = {'solo_lo_suyo': solo_lo_suyo, 've_cola': ve_cola, 've_pacientes': ve_pacientes,
               've_control': ve_control, 'atendidos_hoy': None, 'nuevos_hoy': None,
               'proximos': None, 'atendiendo': [], 'colas': None}

    if ve_cola:
        consultas = Consulta.objects.filter(activo=True, expediente__clinica__in=clinicas)
        if solo_lo_suyo:
            consultas = consultas.filter(doctor=usuario)
        en_espera = Q(inicio__isnull=True, cierre__isnull=True)
        cifras = {
            'en_espera': Count('pk', filter=en_espera),
            'emergencias': Count('pk', filter=en_espera & Q(es_emergencia=True)),
            'en_consulta': Count('pk', filter=Q(inicio__isnull=False, cierre__isnull=True)),
        }
        if ve_control:
            # Con inicio: un retiro tambien se cierra, pero nunca se atendio.
            cifras['atendidos_hoy'] = Count('pk', filter=Q(inicio__isnull=False, cierre__date=hoy))
        # Una sola consulta a la base para todas las cifras.
        resumen.update(consultas.aggregate(**cifras))

    if ve_pacientes and ve_control:
        resumen['nuevos_hoy'] = Expediente.objects.filter(clinica__in=clinicas, fecha_apertura=hoy).count()

    if usuario.has_perm('consultas.change_consulta'):
        propias = Consulta.objects.filter(
            doctor=usuario, activo=True, cierre__isnull=True, expediente__clinica=clinica,
        ).select_related('expediente__persona')
        # "Continuar" abre la atencion, que exige tambien ver el expediente: sin ese permiso daria 403.
        if usuario.has_perm('pacientes.view_expediente'):
            resumen['atendiendo'] = list(propias.filter(inicio__isnull=False).order_by('inicio'))
        resumen['proximos'] = list(
            propias.filter(inicio__isnull=True).order_by('-es_emergencia', 'hora_llegada', 'fecha_creacion')[:4]
        )

    if usuario.has_perms(PERMISOS_ENFERMERIA):
        de_la_clinica = Q(consultas_atendidas__activo=True, consultas_atendidas__expediente__clinica__in=clinicas,
                          consultas_atendidas__cierre__isnull=True)
        resumen['colas'] = _medicos_disponibles(clinicas).annotate(
            en_espera=Count('consultas_atendidas', distinct=True,
                            filter=de_la_clinica & Q(consultas_atendidas__inicio__isnull=True)),
            en_consulta=Count('consultas_atendidas', distinct=True,
                              filter=de_la_clinica & Q(consultas_atendidas__inicio__isnull=False)),
        )

    return resumen
