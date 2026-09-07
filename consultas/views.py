import time
import uuid
from datetime import date

from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.contrib import messages
from django.db.models import F, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.views.decorators.clickjacking import xframe_options_sameorigin

from core.paginacion import es_ajax, paginar
from pacientes.models import Expediente
from .documentos import generar_pdf
from .forms import (AntecedenteForm, ConsultaClinicaForm, ConsultaManualForm,
                    DocumentoMedicoForm)
from .models import Antecedente, Consulta, Incapacidad


def expediente_autorizado(request, expediente_id):
    expediente = get_object_or_404(Expediente.objects.select_related('persona', 'clinica'),
                                  pk=expediente_id, activo=True, persona__activo=True, clinica__activo=True)
    if not request.user.clinicas.filter(pk=expediente.clinica_id).exists():
        raise PermissionDenied
    return expediente


def consulta_autorizada(request, consulta_id):
    consulta = get_object_or_404(Consulta.objects.select_related('doctor', 'expediente__persona',
                                                               'expediente__clinica'), pk=consulta_id, activo=True)
    expediente_autorizado(request, consulta.expediente_id)
    return consulta


def datos_documento(consulta, datos):
    return dict(consulta=consulta, tipo=datos['tipo'], motivo=datos['motivo'],
                dias=datos.get('dias'), fecha_inicio_incapacidad=datos.get('fecha_inicio_incapacidad'),
                fecha=timezone.localdate(),
                fecha_atencion=timezone.localdate(consulta.inicio) if consulta.inicio else timezone.localdate())


def recuperar_previa(request, previa_id):
    dato = request.session.get('documentos_previas', {}).get(str(previa_id))
    if (not dato or time.time() - dato['creada'] > 1800
            or dato['campos'].get('tipo') != Incapacidad.Tipo.INCAPACIDAD
            or 'fecha_inicio_incapacidad' not in dato['campos']):
        raise Http404('La vista previa venció. Vuelva al formulario para revisarla.')
    consulta = consulta_autorizada(request, dato['consulta_id'])
    campos = dict(dato['campos'])
    for campo in ('fecha', 'fecha_inicio_incapacidad', 'fecha_atencion'):
        campos[campo] = date.fromisoformat(campos[campo]) if campos[campo] else None
    # El nombre se copia del perfil que emite y ya no se actualiza: el
    # documento debe seguir diciendo quien lo firmo el dia que se emitio.
    # El JVPM no se copia -- se lee de `creado_por`, no cambia con el tiempo.
    return Incapacidad(consulta=consulta, solicitud_id=previa_id, creado_por=request.user,
                      doctor_nombre=request.user.get_full_name() or request.user.username,
                      **campos)


@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_incapacidad'), raise_exception=True)
def lista_documentos(request, expediente_id):
    expediente = expediente_autorizado(request, expediente_id)
    documentos = Incapacidad.objects.select_related('creado_por', 'consulta__doctor').filter(consulta__expediente=expediente, activo=True).order_by('-fecha', '-pk')
    return render(request, 'consultas/lista_documentos.html', {
        'expediente': expediente, 'pagina': paginar(documentos, request),
        'consultas': expediente.consultas.filter(activo=True).order_by('-inicio'),
    })


@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_incapacidad', 'consultas.add_incapacidad'), raise_exception=True)
def nuevo_documento(request, consulta_id):
    consulta = consulta_autorizada(request, consulta_id)
    inicial = {'motivo': consulta.diagnostico or consulta.motivo,
               'inicio_opcion': 'hoy', 'fecha_inicio_incapacidad': timezone.localdate()}
    editar = request.GET.get('previa')
    if editar:
        try:
            anterior = recuperar_previa(request, uuid.UUID(editar))
        except ValueError:
            raise Http404
        if anterior.consulta_id != consulta.pk:
            raise Http404
        inicial.update(tipo=anterior.tipo, motivo=anterior.motivo, dias=anterior.dias,
                       inicio_opcion='personalizada' if anterior.fecha_inicio_incapacidad else 'hoy',
                       fecha_inicio_incapacidad=anterior.fecha_inicio_incapacidad)
    form = DocumentoMedicoForm(request.POST if request.method == 'POST' else None, initial=inicial)
    if request.method == 'POST' and form.is_valid():
        campos = datos_documento(consulta, form.cleaned_data)
        campos.pop('consulta')
        for k, v in campos.items():
            if isinstance(v, date): campos[k] = v.isoformat()
        previa_id = str(uuid.uuid4())
        previas = {k: v for k, v in request.session.get('documentos_previas', {}).items()
                   if time.time() - v['creada'] < 1800}
        if len(previas) >= 10:
            del previas[min(previas, key=lambda k: previas[k]['creada'])]
        previas[previa_id] = {'creada': time.time(), 'consulta_id': consulta.pk, 'campos': campos}
        request.session['documentos_previas'] = previas
        return redirect('consultas:previsualizar_documento', previa_id=previa_id)
    return render(request, 'consultas/form_documento.html', {
        'form': form, 'consulta': consulta, 'hoy': timezone.localdate().isoformat(),
        'motivo_consulta': consulta.motivo, 'diagnostico_consulta': consulta.diagnostico or consulta.motivo,
    })


@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_incapacidad', 'consultas.add_incapacidad'), raise_exception=True)
def previsualizar_documento(request, previa_id):
    documento = recuperar_previa(request, previa_id)
    return render(request, 'consultas/ver_documento.html', {'documento': documento, 'previa_id': previa_id})


@never_cache
@xframe_options_sameorigin
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_incapacidad', 'consultas.add_incapacidad'), raise_exception=True)
def pdf_previa(request, previa_id):
    return respuesta_pdf(recuperar_previa(request, previa_id), borrador=True)


@require_POST
@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_incapacidad', 'consultas.add_incapacidad'), raise_exception=True)
def emitir_documento(request, previa_id):
    documento = recuperar_previa(request, previa_id)
    existente = Incapacidad.objects.filter(solicitud_id=previa_id).first()
    if existente:
        return redirect('consultas:ver_documento', documento_id=existente.pk)
    # Una vista previa del día anterior se revisa otra vez antes de emitir.
    if documento.fecha != timezone.localdate():
        return redirect('consultas:nuevo_documento', consulta_id=documento.consulta_id)
    with transaction.atomic():
        # Serializa emisiones de la misma consulta, incluido un doble clic.
        Consulta.objects.select_for_update().get(pk=documento.consulta_id)
        existente = Incapacidad.objects.filter(solicitud_id=previa_id).first()
        if existente:
            return redirect('consultas:ver_documento', documento_id=existente.pk)
        documento.creado_por = documento.modificado_por = request.user
        documento.save()
        documento.folio = f'CM-{documento.pk:08d}'
        documento.save(update_fields=['folio'])
    return redirect('consultas:ver_documento', documento_id=documento.pk)


def documento_autorizado(request, documento_id):
    documento = get_object_or_404(Incapacidad.objects.select_related('creado_por', 'consulta__doctor', 'consulta__expediente__persona', 'consulta__expediente__clinica'), pk=documento_id, activo=True)
    expediente_autorizado(request, documento.consulta.expediente_id)
    return documento


@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_incapacidad'), raise_exception=True)
def ver_documento(request, documento_id):
    return render(request, 'consultas/ver_documento.html', {
        'documento': documento_autorizado(request, documento_id),
    })


def respuesta_pdf(documento, borrador=False, descargar=False):
    respuesta = HttpResponse(generar_pdf(documento, borrador=borrador), content_type='application/pdf')
    modo = 'attachment' if descargar else 'inline'
    nombre = 'vista-previa' if borrador else documento.folio
    respuesta['Content-Disposition'] = f'{modo}; filename="{nombre}.pdf"'
    respuesta['X-Content-Type-Options'] = 'nosniff'
    return respuesta


@never_cache
@xframe_options_sameorigin
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_incapacidad'), raise_exception=True)
def pdf_documento(request, documento_id):
    return respuesta_pdf(documento_autorizado(request, documento_id), descargar=request.GET.get('descargar') == '1')


# --------------------------------------------------------------------------
# HU-EXP-17/18/19 -- registrar, atender, finalizar, historial y detalle.
# La consulta es el molde: todos los documentos cuelgan de ella.
# --------------------------------------------------------------------------

def consulta_editable(request, consulta_id):
    """Consulta que todavia se puede escribir. Cerrada = solo lectura."""
    consulta = consulta_autorizada(request, consulta_id)
    if consulta.cerrada:
        raise Http404('La consulta ya fue finalizada.')
    return consulta


@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.add_consulta'), raise_exception=True)
def nueva_consulta(request, expediente_id):
    """
    Registro manual de una atencion (HU-EXP-17). Es el camino de hoy y el
    de siempre para lo que se atendio en papel: la doctora dicta fecha y
    hora reales. Cuando exista la cola, la consulta llegara ya creada.
    """
    expediente = expediente_autorizado(request, expediente_id)
    # Nunca dos consultas abiertas del mismo paciente: se retoma la que hay,
    # asi no queda media atencion perdida ni se atiende dos veces en paralelo.
    abierta = Consulta.objects.filter(expediente=expediente, cierre__isnull=True, activo=True).first()
    if abierta:
        messages.info(request, 'Este paciente ya tiene una consulta sin finalizar; se retomó esa.')
        return redirect('consultas:atender_consulta', consulta_id=abierta.pk)

    form = ConsultaManualForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        consulta = Consulta.objects.create(
            expediente=expediente, doctor=request.user,
            # Nombre congelado al crear: si el perfil cambia despues, esta
            # consulta sigue diciendo quien atendio ese dia.
            doctor_nombre=request.user.get_full_name() or request.user.username,
            inicio=form.cleaned_data['inicio'], motivo='',
            creado_por=request.user, modificado_por=request.user,
        )
        return redirect('consultas:atender_consulta', consulta_id=consulta.pk)

    ahora = timezone.localtime()
    return render(request, 'consultas/nueva_consulta.html', {
        'expediente': expediente, 'form': form,
        'hoy': ahora.date().isoformat(), 'hora_actual': ahora.strftime('%H:%M'),
    })


@require_POST
@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.change_consulta'), raise_exception=True)
def iniciar_consulta(request, consulta_id):
    """
    Marca el inicio de la atencion (criterio nuevo de HU-EXP-17). Es el
    boton que pulsara la doctora desde la cola de Kevin; abrir el
    expediente no inicia nada por si solo.
    """
    consulta = consulta_editable(request, consulta_id)
    if consulta.en_cola:
        consulta.inicio = timezone.now()
        consulta.modificado_por = request.user
        consulta.save(update_fields=['inicio', 'modificado_por', 'fecha_modificacion'])
    return redirect('consultas:atender_consulta', consulta_id=consulta.pk)


@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.change_consulta'), raise_exception=True)
def atender_consulta(request, consulta_id):
    """Pantalla de atencion: los ocho campos, con preguardado automatico."""
    consulta = consulta_autorizada(request, consulta_id)
    if consulta.cerrada:
        return redirect('consultas:ver_consulta', consulta_id=consulta.pk)
    return render(request, 'consultas/atender_consulta.html', {
        'consulta': consulta, 'form': ConsultaClinicaForm(instance=consulta, borrador=True),
        # Los documentos se emiten durante la atencion, no despues: es
        # cuando la doctora tiene al paciente enfrente (mockup).
        'incapacidades': consulta.incapacidades.filter(activo=True).order_by('-fecha', '-pk'),
        'form_incapacidad': DocumentoMedicoForm(initial={
            'motivo': consulta.diagnostico or consulta.motivo, 'inicio_opcion': 'hoy',
            'fecha_inicio_incapacidad': timezone.localdate(),
        }),
        # Identifica este dibujado del formulario: dos envios del mismo no
        # crean dos documentos.
        'solicitud_id': uuid.uuid4(),
        'antecedentes': consulta.expediente.antecedentes.filter(activo=True),
        'signos': getattr(consulta, 'signos_vitales', None),
    })


@require_POST
@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.change_consulta'), raise_exception=True)
def guardar_borrador(request, consulta_id):
    """
    Preguardado: lo que la doctora escribe no se pierde si cierra la
    ventana por error. Se guarda en el servidor, sobre la misma fila --
    no en el navegador, porque cambiar de maquina perderia el texto.
    """
    consulta = consulta_autorizada(request, consulta_id)
    if consulta.cerrada:
        return JsonResponse({'ok': False, 'mensaje': 'La consulta ya fue finalizada.'}, status=409)
    form = ConsultaClinicaForm(request.POST, instance=consulta, borrador=True)
    if not form.is_valid():
        return JsonResponse({'ok': False, 'mensaje': 'No se pudo guardar.'}, status=400)
    consulta = form.save(commit=False)
    consulta.modificado_por = request.user
    consulta.save()
    return JsonResponse({'ok': True, 'hora': timezone.localtime().strftime('%H:%M')})


@require_POST
@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.change_consulta'), raise_exception=True)
def finalizar_consulta(request, consulta_id):
    """
    Cierra la atencion. Es una accion propia, independiente de emitir la
    receta -- cerrar por receta se presta a error humano (acuerdo del
    05/09/2026, deja obsoleta la regla anterior).
    """
    consulta = consulta_autorizada(request, consulta_id)
    if consulta.cerrada:
        return redirect('consultas:ver_consulta', consulta_id=consulta.pk)
    # Finaliza sobre lo ya preguardado: el modal de confirmacion manda su
    # propio POST y no arrastra el formulario, y el borrador ya esta en la
    # fila. El motivo es el unico campo que la consulta no puede no tener.
    if not consulta.motivo.strip():
        messages.error(request, 'Escriba el motivo de consulta antes de finalizar.')
        return redirect('consultas:atender_consulta', consulta_id=consulta.pk)
    consulta.modificado_por = request.user
    consulta.cierre = timezone.now()
    if consulta.inicio is None:
        consulta.inicio = consulta.cierre
    consulta.save()
    messages.success(request, 'Consulta finalizada.')
    return redirect('consultas:ver_consulta', consulta_id=consulta.pk)


@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_consulta'), raise_exception=True)
def historial_consultas(request, expediente_id):
    """
    HU-EXP-18: listado cronologico con buscador en vivo -- mismo patron
    de listado sin recarga que ya usan Pacientes, Usuarios y Bitacora.
    """
    expediente = expediente_autorizado(request, expediente_id)
    consultas = Consulta.objects.filter(expediente=expediente, activo=True)

    consulta_texto = request.GET.get('q', '').strip()
    if consulta_texto:
        consultas = consultas.filter(
            Q(motivo__unaccent__icontains=consulta_texto)
            | Q(diagnostico__unaccent__icontains=consulta_texto)
            | Q(tratamiento__unaccent__icontains=consulta_texto)
            | Q(doctor_nombre__unaccent__icontains=consulta_texto)
        )

    # Las que siguen en la cola no tienen `inicio`: van al final, no primero.
    consultas = consultas.order_by(F('inicio').desc(nulls_last=True), '-pk')
    contexto = {
        'expediente': expediente, 'consulta': consulta_texto,
        'total': consultas.count(), 'pagina': paginar(consultas, request),
    }
    plantilla = ('consultas/resultados_consultas.html' if es_ajax(request)
                 else 'consultas/historial_consultas.html')
    return render(request, plantilla, contexto)


@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_consulta'), raise_exception=True)
def ver_consulta(request, consulta_id):
    """HU-EXP-19: detalle con los campos clinicos y los documentos emitidos."""
    consulta = consulta_autorizada(request, consulta_id)
    # Las etiquetas salen del formulario: una sola fuente, para que el
    # detalle y la pantalla de atencion nunca nombren distinto un campo.
    etiquetas = ConsultaClinicaForm().fields
    return render(request, 'consultas/ver_consulta.html', {
        'consulta': consulta,
        'campos': [(campo.label, getattr(consulta, nombre)) for nombre, campo in etiquetas.items()],
        'incapacidades': consulta.incapacidades.filter(activo=True).order_by('-fecha', '-pk'),
    })


# --------------------------------------------------------------------------
# HU-EXP-07 -- antecedentes del paciente. Cuelgan del expediente, no de la
# consulta: son permanentes y no se vuelven a preguntar en cada visita.
# --------------------------------------------------------------------------

@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_antecedente'), raise_exception=True)
def antecedentes(request, expediente_id):
    expediente = expediente_autorizado(request, expediente_id)
    form = AntecedenteForm(request.POST or None)
    if request.method == 'POST':
        if not request.user.has_perm('consultas.add_antecedente'):
            raise PermissionDenied
        if form.is_valid():
            antecedente = form.save(commit=False)
            antecedente.expediente = expediente
            antecedente.creado_por = antecedente.modificado_por = request.user
            antecedente.save()
            messages.success(request, 'Antecedente agregado.')
            # Post/redirect/get: recargar no vuelve a agregarlo.
            return redirect('consultas:antecedentes', expediente_id=expediente.pk)
    return render(request, 'consultas/antecedentes.html', {
        'expediente': expediente, 'form': form,
        'antecedentes': expediente.antecedentes.filter(activo=True),
    })


@require_POST
@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.change_antecedente'), raise_exception=True)
def desactivar_antecedente(request, antecedente_id):
    """Nada se elimina (regla del proyecto): se desactiva con `activo`."""
    antecedente = get_object_or_404(
        Antecedente.objects.select_related('expediente'), pk=antecedente_id, activo=True)
    expediente_autorizado(request, antecedente.expediente_id)
    antecedente.activo = False
    antecedente.modificado_por = request.user
    antecedente.save(update_fields=['activo', 'modificado_por', 'fecha_modificacion'])
    messages.success(request, 'Antecedente retirado del expediente.')
    return redirect('consultas:antecedentes', expediente_id=antecedente.expediente_id)


@require_POST
@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_incapacidad',
                      'consultas.add_incapacidad'), raise_exception=True)
def agregar_incapacidad(request, consulta_id):
    """
    Emite la incapacidad SIN salir de la pantalla de atencion, como en el
    mockup ("Agregar documento (opcional)"). La pantalla aparte con vista
    previa sigue existiendo para emitirla despues, desde el detalle.

    Contra el doble clic: el formulario trae un `solicitud_id` generado al
    dibujarlo; si ya existe un documento con ese identificador, no se crea
    otro. Es la misma proteccion que usa el camino con vista previa.
    """
    consulta = consulta_autorizada(request, consulta_id)
    try:
        solicitud = uuid.UUID(request.POST.get('solicitud_id', ''))
    except ValueError:
        raise Http404
    if Incapacidad.objects.filter(solicitud_id=solicitud).exists():
        return redirect('consultas:atender_consulta', consulta_id=consulta.pk)

    form = DocumentoMedicoForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Revise los datos de la incapacidad: %s' %
                       '; '.join(e for errores in form.errors.values() for e in errores))
        return redirect('consultas:atender_consulta', consulta_id=consulta.pk)

    campos = datos_documento(consulta, form.cleaned_data)
    with transaction.atomic():
        Consulta.objects.select_for_update().get(pk=consulta.pk)
        if Incapacidad.objects.filter(solicitud_id=solicitud).exists():
            return redirect('consultas:atender_consulta', consulta_id=consulta.pk)
        documento = Incapacidad.objects.create(
            **campos, solicitud_id=solicitud,
            doctor_nombre=request.user.get_full_name() or request.user.username,
            creado_por=request.user, modificado_por=request.user,
        )
        documento.folio = f'CM-{documento.pk:08d}'
        documento.save(update_fields=['folio'])
    messages.success(request, f'Incapacidad {documento.folio} agregada a la consulta.')
    return redirect('consultas:atender_consulta', consulta_id=consulta.pk)
