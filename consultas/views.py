import time
import uuid
from datetime import date

from django.contrib.auth.context_processors import PermWrapper
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.contrib import messages
from django.db.models import F, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.views.decorators.clickjacking import xframe_options_sameorigin

from core.paginacion import es_ajax, paginar
from pacientes.models import Expediente
from .documentos import (generar_pdf, generar_pdf_orden, generar_pdf_receta,
                         generar_pdf_referencia)
from .forms import (AdjuntoForm, AntecedenteForm, AplicacionForm, ConsultaClinicaForm,
                    ConsultaManualForm, ControlPosteriorForm, DocumentoMedicoForm,
                    OrdenExamenForm, RecetaForm, ReferenciaMedicaForm,
                    ReprogramarControlForm)
from .models import (Adjunto, Antecedente, Aplicacion, Consulta, ControlPosterior,
                     DetalleOrdenExamen, DetalleReceta, Incapacidad,
                     OrdenExamen, Receta, ReferenciaMedica, SignosVitales)


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


def consulta_propia(request, consulta_id):
    """
    Consulta que este usuario puede atender. Leerla la puede cualquiera
    de la clinica (consulta_autorizada); escribir en ella solo su propio
    doctor, o quien administra el sistema. Sin esto, un doctor podria
    escribir en la consulta de otro y emitir documentos que salen
    firmados con el nombre del otro. Pasar un paciente a otro medico se
    hace reasignando, no entrando a su consulta.
    """
    consulta = consulta_autorizada(request, consulta_id)
    if consulta.doctor_id != request.user.pk and not request.user.has_perm('auth.change_group'):
        raise PermissionDenied
    return consulta


def consulta_para_documento(request, consulta_id):
    """Consulta sobre la que se puede emitir un documento: no, si el paciente se retiró sin atenderse."""
    consulta = consulta_autorizada(request, consulta_id)
    if consulta.retirada:
        raise Http404('El paciente se retiró sin atenderse; no se emiten documentos sobre esta visita.')
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
    consulta = consulta_para_documento(request, consulta_id)
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

def consulta_en_curso(usuario, excepto=None):
    """Consulta que el medico ya inicio y no ha finalizado: atiende uno a la vez."""
    return (Consulta.objects.filter(doctor=usuario, inicio__isnull=False, cierre__isnull=True, activo=True)
            .exclude(pk=excepto).select_related('expediente__persona').first())


def consulta_editable(request, consulta_id):
    """Consulta que todavia se puede escribir. Cerrada = solo lectura."""
    consulta = consulta_propia(request, consulta_id)
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
    en_curso = consulta_en_curso(request.user)
    if en_curso:
        messages.error(request, f'Finalice la consulta de {en_curso.expediente.persona} antes de registrar otra.')
        return redirect('pacientes:ver_expediente', expediente_id=expediente.pk)

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
        # Una emergencia no espera a que termine la consulta en curso.
        en_curso = None if consulta.es_emergencia else consulta_en_curso(request.user, excepto=consulta.pk)
        if en_curso:
            messages.error(request, f'Finalice la consulta de {en_curso.expediente.persona} '
                                    'antes de atender a otro paciente.')
            return redirect('pacientes:cola_consultas')
        consulta.inicio = timezone.now()
        consulta.modificado_por = request.user
        consulta.save(update_fields=['inicio', 'modificado_por', 'fecha_modificacion'])
    return redirect('consultas:atender_consulta', consulta_id=consulta.pk)


@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.change_consulta'), raise_exception=True)
def atender_consulta(request, consulta_id):
    """Pantalla de atencion: los ocho campos, con preguardado automatico."""
    consulta = consulta_propia(request, consulta_id)
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
        'referencias': consulta.referencias.filter(activo=True).order_by('-fecha', '-pk'),
        'form_referencia': ReferenciaMedicaForm(),
        'controles': consulta.controles.filter(activo=True).order_by('fecha_control'),
        'form_control': ControlPosteriorForm(),
        'aplicaciones': consulta.aplicaciones.filter(activo=True).order_by('-pk'),
        'form_aplicacion': AplicacionForm(),
        'ordenes': consulta.ordenes_examen.filter(activo=True).prefetch_related('detalles').order_by('-pk'),
        'form_orden': OrdenExamenForm(),
        'receta': getattr(consulta, 'receta', None),
        'form_receta': RecetaForm(),
        'antecedentes': consulta.expediente.antecedentes.filter(activo=True),
        'signos': getattr(consulta, 'signos_vitales', None),
    })


@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.change_consulta'), raise_exception=True)
def signos_vitales_consulta(request, consulta_id):
    """Tarjeta de signos vitales sola: la atencion la vuelve a pedir para ver correcciones de enfermeria."""
    consulta = consulta_propia(request, consulta_id)
    signos = SignosVitales.objects.select_related('modificado_por').filter(consulta=consulta).first()
    return render(request, 'consultas/signos_vitales.html', {'signos': signos})


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
    consulta = consulta_propia(request, consulta_id)
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
    consulta = consulta_propia(request, consulta_id)
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
        'referencias': consulta.referencias.filter(activo=True).order_by('-fecha', '-pk'),
        'controles': consulta.controles.filter(activo=True).order_by('fecha_control'),
        'aplicaciones': consulta.aplicaciones.filter(activo=True).order_by('-pk'),
        'reasignaciones': consulta.reasignaciones.select_related(
            'medico_anterior', 'medico_nuevo', 'reasignado_por',
        ),
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

    # Cada antecedente lleva su propio formulario ya lleno, para corregirlo
    # en su lugar. Va sin `prefix` porque cada uno viaja en su propio
    # <form>, asi que los nombres de los campos no se pisan.
    registrados = list(expediente.antecedentes.filter(activo=True))
    for antecedente in registrados:
        antecedente.form_edicion = AntecedenteForm(instance=antecedente)

    return render(request, 'consultas/antecedentes.html', {
        'expediente': expediente, 'form': form, 'antecedentes': registrados,
    })


def _antecedente_autorizado(request, antecedente_id):
    antecedente = get_object_or_404(
        Antecedente.objects.select_related('expediente'), pk=antecedente_id, activo=True)
    expediente_autorizado(request, antecedente.expediente_id)
    return antecedente


@require_POST
@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.change_antecedente'), raise_exception=True)
def editar_antecedente(request, antecedente_id):
    """
    Corregir un antecedente ya registrado (criterio del Word: "la doctora
    puede registrar y EDITAR los antecedentes"). Quedo sin construir el
    06/09/2026 y se completo el 21/09/2026.

    Se corrige la fila, no se crea otra: un antecedente es un dato
    permanente del paciente, no un documento emitido. Si se escribio mal
    "Penicilina" o se precisa el diagnostico, lo que vale es el dato
    corregido -- guardar las dos versiones dejaria dos alergias donde hay
    una. Quien lo corrigio y cuando quedan en `modificado_por` y
    `fecha_modificacion`.

    Distinto de corregir un documento YA EMITIDO (incapacidad, referencia):
    eso sigue siendo punto a debatir, porque el paciente ya se llevo el
    papel.
    """
    antecedente = _antecedente_autorizado(request, antecedente_id)
    form = AntecedenteForm(request.POST, instance=antecedente)
    if form.is_valid():
        antecedente = form.save(commit=False)
        antecedente.modificado_por = request.user
        antecedente.save()
        messages.success(request, 'Antecedente corregido.')
    else:
        messages.error(request, 'Revise el antecedente: %s' %
                       '; '.join(e for errores in form.errors.values() for e in errores))
    return redirect('consultas:antecedentes', expediente_id=antecedente.expediente_id)


@require_POST
@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.change_antecedente'), raise_exception=True)
def desactivar_antecedente(request, antecedente_id):
    """Nada se elimina (regla del proyecto): se desactiva con `activo`."""
    antecedente = _antecedente_autorizado(request, antecedente_id)
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
    consulta = consulta_para_documento(request, consulta_id)
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


# --------------------------------------------------------------------------
# HU-EXP-23 -- referencia medica. Mismo patron que la constancia: se agrega
# durante la atencion, sin salir de la consulta, y tambien despues.
# --------------------------------------------------------------------------

@require_POST
@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_referenciamedica',
                      'consultas.add_referenciamedica'), raise_exception=True)
def agregar_referencia(request, consulta_id):
    consulta = consulta_para_documento(request, consulta_id)
    form = ReferenciaMedicaForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Revise los datos de la referencia: %s' %
                       '; '.join(e for errores in form.errors.values() for e in errores))
        return redirect('consultas:atender_consulta', consulta_id=consulta.pk)
    referencia = form.save(commit=False)
    referencia.consulta = consulta
    # Mismo criterio que la constancia: el nombre se congela al emitir.
    referencia.doctor_nombre = request.user.get_full_name() or request.user.username
    referencia.creado_por = referencia.modificado_por = request.user
    referencia.save()
    messages.success(request, f'Referencia a {referencia.especialidad} agregada a la consulta.')
    destino = 'atender_consulta' if not consulta.cerrada else 'ver_consulta'
    return redirect(f'consultas:{destino}', consulta_id=consulta.pk)


def referencia_autorizada(request, referencia_id):
    referencia = get_object_or_404(
        ReferenciaMedica.objects.select_related(
            'creado_por', 'consulta__doctor', 'consulta__expediente__persona',
            'consulta__expediente__clinica'),
        pk=referencia_id, activo=True)
    expediente_autorizado(request, referencia.consulta.expediente_id)
    return referencia


@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_referenciamedica'), raise_exception=True)
def lista_referencias(request, expediente_id):
    expediente = expediente_autorizado(request, expediente_id)
    referencias = ReferenciaMedica.objects.select_related('creado_por', 'consulta__doctor').filter(
        consulta__expediente=expediente, activo=True).order_by('-fecha', '-pk')
    return render(request, 'consultas/lista_referencias.html', {
        'expediente': expediente, 'pagina': paginar(referencias, request),
    })


@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_referenciamedica'), raise_exception=True)
def ver_referencia(request, referencia_id):
    return render(request, 'consultas/ver_referencia.html', {
        'referencia': referencia_autorizada(request, referencia_id),
    })


@never_cache
@xframe_options_sameorigin
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_referenciamedica'), raise_exception=True)
def pdf_referencia(request, referencia_id):
    referencia = referencia_autorizada(request, referencia_id)
    respuesta = HttpResponse(generar_pdf_referencia(referencia), content_type='application/pdf')
    modo = 'attachment' if request.GET.get('descargar') == '1' else 'inline'
    respuesta['Content-Disposition'] = f'{modo}; filename="referencia-{referencia.pk}.pdf"'
    respuesta['X-Content-Type-Options'] = 'nosniff'
    return respuesta


# --------------------------------------------------------------------------
# HU-EXP-24 -- control posterior. Se programa desde la consulta y se le da
# seguimiento desde el expediente: no genera documento ni PDF.
# --------------------------------------------------------------------------

@require_POST
@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_controlposterior',
                      'consultas.add_controlposterior'), raise_exception=True)
def agregar_control(request, consulta_id):
    consulta = consulta_para_documento(request, consulta_id)
    form = ControlPosteriorForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Revise los datos del control: %s' %
                       '; '.join(e for errores in form.errors.values() for e in errores))
    else:
        control = form.save(commit=False)
        control.consulta = consulta
        control.creado_por = control.modificado_por = request.user
        control.save()
        messages.success(request, f'Control programado para el {control.fecha_control:%d/%m/%Y}.')
    destino = 'ver_consulta' if consulta.cerrada else 'atender_consulta'
    return redirect(f'consultas:{destino}', consulta_id=consulta.pk)


def control_autorizado(request, control_id):
    control = get_object_or_404(
        ControlPosterior.objects.select_related('consulta__expediente__persona',
                                               'consulta__expediente__clinica'),
        pk=control_id, activo=True)
    expediente_autorizado(request, control.consulta.expediente_id)
    return control


@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_controlposterior'), raise_exception=True)
def lista_controles(request, expediente_id):
    """
    Version simple, como recomendo Kevin: los pendientes primero y arriba,
    que es lo unico que hay que mirar. Sin pantalla grande ni notificaciones.
    """
    expediente = expediente_autorizado(request, expediente_id)
    controles = ControlPosterior.objects.filter(
        consulta__expediente=expediente, activo=True).select_related('consulta')
    return render(request, 'consultas/lista_controles.html', {
        'expediente': expediente,
        'pendientes': controles.filter(estado=ControlPosterior.Estado.PENDIENTE).order_by('fecha_control'),
        'resueltos': controles.exclude(estado=ControlPosterior.Estado.PENDIENTE).order_by('-fecha_control'),
        'form_reprogramar': ReprogramarControlForm(),
        'estados': ControlPosterior.Estado.choices,
    })


@require_POST
@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.change_controlposterior'), raise_exception=True)
def cambiar_estado_control(request, control_id):
    control = control_autorizado(request, control_id)
    estado = request.POST.get('estado')
    if estado not in ControlPosterior.Estado.values:
        raise Http404
    control.estado = estado
    control.modificado_por = request.user
    control.save(update_fields=['estado', 'modificado_por', 'fecha_modificacion'])
    messages.success(request, f'Control marcado como {control.get_estado_display().lower()}.')
    return redirect('consultas:lista_controles', expediente_id=control.consulta.expediente_id)


@require_POST
@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.change_controlposterior'), raise_exception=True)
def reprogramar_control(request, control_id):
    control = control_autorizado(request, control_id)
    form = ReprogramarControlForm(request.POST, instance=control)
    if form.is_valid():
        control = form.save(commit=False)
        control.modificado_por = request.user
        # Reprogramar lo devuelve a pendiente: la fecha nueva todavia no ocurrio.
        control.estado = ControlPosterior.Estado.PENDIENTE
        control.save()
        messages.success(request, f'Control reprogramado para el {control.fecha_control:%d/%m/%Y}.')
    else:
        messages.error(request, '; '.join(e for errores in form.errors.values() for e in errores))
    return redirect('consultas:lista_controles', expediente_id=control.consulta.expediente_id)


# --------------------------------------------------------------------------
# HU-EXP-21 -- aplicaciones y servicios. La doctora los indica en la
# consulta; quien los aplica los marca ejecutados despues.
# --------------------------------------------------------------------------

@require_POST
@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_aplicacion',
                      'consultas.add_aplicacion'), raise_exception=True)
def agregar_aplicacion(request, consulta_id):
    consulta = consulta_para_documento(request, consulta_id)
    form = AplicacionForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Revise los datos de la aplicación: %s' %
                       '; '.join(e for errores in form.errors.values() for e in errores))
    else:
        aplicacion = form.save(commit=False)
        aplicacion.consulta = consulta
        aplicacion.creado_por = aplicacion.modificado_por = request.user
        aplicacion.save()
        messages.success(request, f'{aplicacion.get_tipo_display()} indicada en la consulta.')
    destino = 'ver_consulta' if consulta.cerrada else 'atender_consulta'
    return redirect(f'consultas:{destino}', consulta_id=consulta.pk)


@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_aplicacion'), raise_exception=True)
def lista_aplicaciones(request, expediente_id):
    expediente = expediente_autorizado(request, expediente_id)
    aplicaciones = Aplicacion.objects.filter(
        consulta__expediente=expediente, activo=True).select_related('consulta', 'ejecutada_por')
    return render(request, 'consultas/lista_aplicaciones.html', {
        'expediente': expediente,
        'pendientes': aplicaciones.filter(ejecutada=False).order_by('-pk'),
        'ejecutadas': aplicaciones.filter(ejecutada=True).order_by('-fecha_ejecucion'),
    })


@require_POST
@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.change_aplicacion'), raise_exception=True)
def marcar_aplicacion(request, aplicacion_id):
    """
    Deja constancia de quien aplico y cuando (criterio de HU-EXP-21). Se
    registra al usuario de la sesion: es quien lo esta haciendo.
    """
    aplicacion = get_object_or_404(
        Aplicacion.objects.select_related('consulta__expediente'), pk=aplicacion_id, activo=True)
    expediente_autorizado(request, aplicacion.consulta.expediente_id)
    if not aplicacion.ejecutada:
        aplicacion.ejecutada = True
        aplicacion.ejecutada_por = request.user
        aplicacion.fecha_ejecucion = timezone.now()
        aplicacion.modificado_por = request.user
        aplicacion.save()
        messages.success(request, f'{aplicacion.get_tipo_display()} marcada como aplicada.')
    return redirect('consultas:lista_aplicaciones',
                   expediente_id=aplicacion.consulta.expediente_id)


# --------------------------------------------------------------------------
# HU-EXP-20 -- ordenes de examen. Version sencilla (21/09/2026): tipos de
# examen e indicaciones. Se crean desde la consulta, como los demas
# documentos; la orden suelta llegara con el modulo de Laboratorio.
# --------------------------------------------------------------------------

@require_POST
@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_ordenexamen',
                      'consultas.add_ordenexamen'), raise_exception=True)
def agregar_orden(request, consulta_id):
    consulta = consulta_para_documento(request, consulta_id)
    form = OrdenExamenForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Revise los datos de la orden: %s' %
                       '; '.join(e for errores in form.errors.values() for e in errores))
    else:
        with transaction.atomic():
            orden = OrdenExamen.objects.create(
                persona=consulta.expediente.persona, consulta=consulta,
                indicaciones=form.cleaned_data['indicaciones'],
                # Mismo criterio que el resto: el nombre se congela al emitir.
                doctor_nombre=request.user.get_full_name() or request.user.username,
                creado_por=request.user, modificado_por=request.user,
            )
            DetalleOrdenExamen.objects.bulk_create([
                DetalleOrdenExamen(orden=orden, tipo_examen=tipo,
                                  creado_por=request.user, modificado_por=request.user)
                for tipo in form.cleaned_data['examenes']
            ])
        messages.success(request, 'Orden de exámenes agregada a la consulta.')
    destino = 'ver_consulta' if consulta.cerrada else 'atender_consulta'
    return redirect(f'consultas:{destino}', consulta_id=consulta.pk)


def orden_autorizada(request, orden_id):
    orden = get_object_or_404(
        OrdenExamen.objects.select_related('creado_por', 'persona', 'consulta__doctor',
                                          'consulta__expediente__clinica'),
        pk=orden_id, activo=True)
    expediente_autorizado(request, orden.consulta.expediente_id)
    return orden


@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_ordenexamen'), raise_exception=True)
def lista_ordenes(request, expediente_id):
    expediente = expediente_autorizado(request, expediente_id)
    ordenes = OrdenExamen.objects.filter(
        consulta__expediente=expediente, activo=True,
    ).select_related('creado_por', 'consulta__doctor').prefetch_related('detalles').order_by('-fecha', '-pk')
    return render(request, 'consultas/lista_ordenes.html', {
        'expediente': expediente, 'pagina': paginar(ordenes, request),
    })


@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_ordenexamen'), raise_exception=True)
def ver_orden(request, orden_id):
    return render(request, 'consultas/ver_orden.html', {'orden': orden_autorizada(request, orden_id)})


@never_cache
@xframe_options_sameorigin
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_ordenexamen'), raise_exception=True)
def pdf_orden(request, orden_id):
    orden = orden_autorizada(request, orden_id)
    respuesta = HttpResponse(generar_pdf_orden(orden), content_type='application/pdf')
    modo = 'attachment' if request.GET.get('descargar') == '1' else 'inline'
    respuesta['Content-Disposition'] = f'{modo}; filename="orden-examenes-{orden.pk}.pdf"'
    respuesta['X-Content-Type-Options'] = 'nosniff'
    return respuesta


# --------------------------------------------------------------------------
# HU-EXP-25 -- receta. Una por consulta (uno a uno en la base). Se van
# agregando medicamentos, como el boton "+" del mockup.
#
# ⚠️ Emitirla NO cierra la consulta: eso lo hace "Finalizar consulta", que
# es accion aparte (criterios nuevos del Word, acuerdo del 05/09/2026).
# --------------------------------------------------------------------------

def _receta_de(consulta, usuario):
    """La receta de la consulta; la crea la primera vez que se agrega algo."""
    receta = getattr(consulta, 'receta', None)
    if receta:
        return receta
    receta = Receta.objects.create(
        consulta=consulta, folio='',
        # Nombre congelado al emitir, igual que el resto de documentos.
        doctor_nombre=usuario.get_full_name() or usuario.username,
        creado_por=usuario, modificado_por=usuario,
    )
    # El folio sale del id, como en la constancia. Formato definitivo y
    # correlativo por clinica siguen pendientes de acordar.
    receta.folio = f'R-{receta.pk:08d}'
    receta.save(update_fields=['folio'])
    return receta


@require_POST
@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_receta',
                      'consultas.add_receta'), raise_exception=True)
def _respuesta_receta(request, consulta, mensaje, tipo='success'):
    """
    Lo que se devuelve despues de tocar la receta.

    Si la pidio el navegador por fetch, solo el pedazo que cambio: agregar o
    corregir un medicamento no tiene por que recargar la pantalla de
    atencion. Recargarla movia la pagina de lugar en plena consulta, con el
    paciente enfrente.

    Sin JavaScript se sigue redirigiendo como antes -- el formulario funciona
    igual, solo que recargando.
    """
    receta = Receta.objects.filter(consulta=consulta, activo=True).first()
    if es_ajax(request):
        contexto = {'receta': receta, 'perms': PermWrapper(request.user)}
        return JsonResponse({
            'ok': tipo == 'success',
            'mensaje': mensaje,
            'tipo': tipo,
            'medicamentos': render_to_string('consultas/_receta_medicamentos.html',
                                             contexto, request=request),
            'acciones': render_to_string('consultas/_receta_acciones.html',
                                         contexto, request=request),
        })
    getattr(messages, 'error' if tipo == 'danger' else 'success')(request, mensaje)
    destino = 'ver_consulta' if consulta.cerrada else 'atender_consulta'
    return redirect(f'consultas:{destino}', consulta_id=consulta.pk)


def agregar_medicamento(request, consulta_id):
    consulta = consulta_para_documento(request, consulta_id)
    form = RecetaForm(request.POST)
    if not form.is_valid():
        return _respuesta_receta(request, consulta, 'Revise el medicamento: %s' %
                                 '; '.join(e for errores in form.errors.values() for e in errores),
                                 tipo='danger')
    with transaction.atomic():
        # Serializa dos envios seguidos: la receta se crea una sola vez.
        Consulta.objects.select_for_update().get(pk=consulta.pk)
        receta = _receta_de(consulta, request.user)
        DetalleReceta.objects.create(
            receta=receta, medicamento=form.cleaned_data['medicamento'].strip(),
            dosis=form.cleaned_data['dosis'].strip(),
            duracion=form.cleaned_data['duracion'].strip(),
            creado_por=request.user, modificado_por=request.user,
        )
    return _respuesta_receta(request, consulta,
                             f"{form.cleaned_data['medicamento']} agregado a la receta.")


def _medicamento_autorizado(request, detalle_id):
    detalle = get_object_or_404(
        DetalleReceta.objects.select_related('receta__consulta__expediente'),
        pk=detalle_id, activo=True)
    expediente_autorizado(request, detalle.receta.consulta.expediente_id)
    return detalle


@require_POST
@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.change_receta'), raise_exception=True)
def editar_medicamento(request, detalle_id):
    """
    Corregir un medicamento ya agregado (pedido de Samuel, 21/09/2026).

    Antes solo se podia quitar y volver a escribir entero. Cambiar "cada 8
    horas" por "cada 12" obligaba a teclear las tres casillas otra vez.

    Se corrige en su lugar, no se crea una fila nueva: quien lo corrigio y
    cuando quedan en `modificado_por` y `fecha_modificacion`. La receta aun
    no se ha impreso -- esto es la doctora escribiendola, no una correccion
    a un documento ya entregado.
    """
    detalle = _medicamento_autorizado(request, detalle_id)
    form = RecetaForm(request.POST)
    if not form.is_valid():
        return _respuesta_receta(request, detalle.receta.consulta, 'Revise el medicamento: %s' %
                                 '; '.join(e for errores in form.errors.values() for e in errores),
                                 tipo='danger')
    detalle.medicamento = form.cleaned_data['medicamento'].strip()
    detalle.dosis = form.cleaned_data['dosis'].strip()
    detalle.duracion = form.cleaned_data['duracion'].strip()
    detalle.modificado_por = request.user
    detalle.save(update_fields=['medicamento', 'dosis', 'duracion',
                                'modificado_por', 'fecha_modificacion'])
    return _respuesta_receta(request, detalle.receta.consulta,
                             f'{detalle.medicamento} corregido.')


@require_POST
@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.change_receta'), raise_exception=True)
def quitar_medicamento(request, detalle_id):
    """
    Un medicamento mal puesto se quita antes de imprimir. No se elimina
    (regla del proyecto): se desactiva y deja de salir en el PDF.
    """
    detalle = _medicamento_autorizado(request, detalle_id)
    detalle.activo = False
    detalle.modificado_por = request.user
    detalle.save(update_fields=['activo', 'modificado_por', 'fecha_modificacion'])
    return _respuesta_receta(request, detalle.receta.consulta,
                             f'{detalle.medicamento} quitado de la receta.')


def receta_autorizada(request, receta_id):
    receta = get_object_or_404(
        Receta.objects.select_related('creado_por', 'consulta__doctor',
                                     'consulta__expediente__persona',
                                     'consulta__expediente__clinica'),
        pk=receta_id, activo=True)
    expediente_autorizado(request, receta.consulta.expediente_id)
    return receta


@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_receta'), raise_exception=True)
def lista_recetas(request, expediente_id):
    expediente = expediente_autorizado(request, expediente_id)
    recetas = Receta.objects.filter(
        consulta__expediente=expediente, activo=True,
    ).select_related('creado_por', 'consulta__doctor').prefetch_related('detalles').order_by('-fecha', '-pk')
    return render(request, 'consultas/lista_recetas.html', {
        'expediente': expediente, 'pagina': paginar(recetas, request),
    })


@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_receta'), raise_exception=True)
def ver_receta(request, receta_id):
    return render(request, 'consultas/ver_receta.html', {'receta': receta_autorizada(request, receta_id)})


@never_cache
@xframe_options_sameorigin
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_receta'), raise_exception=True)
def pdf_receta(request, receta_id):
    receta = receta_autorizada(request, receta_id)
    respuesta = HttpResponse(generar_pdf_receta(receta), content_type='application/pdf')
    modo = 'attachment' if request.GET.get('descargar') == '1' else 'inline'
    respuesta['Content-Disposition'] = f'{modo}; filename="receta-{receta.folio}.pdf"'
    respuesta['X-Content-Type-Options'] = 'nosniff'
    return respuesta


# --------------------------------------------------------------------------
# HU-EXP-08 -- adjuntos del expediente. Cuelgan del expediente, no de una
# consulta: un examen que el paciente se hizo por su cuenta no pertenece a
# ninguna visita.
# --------------------------------------------------------------------------

@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_adjunto'), raise_exception=True)
def adjuntos(request, expediente_id):
    expediente = expediente_autorizado(request, expediente_id)
    form = AdjuntoForm(request.POST or None, request.FILES or None)
    if request.method == 'POST':
        if not request.user.has_perm('consultas.add_adjunto'):
            raise PermissionDenied
        if form.is_valid():
            adjunto = form.save(commit=False)
            adjunto.expediente = expediente
            # `creado_por` es el "subido_por" del diagrama, y
            # `fecha_creacion` su "fecha": el criterio de la historia
            # ("cada adjunto guarda la fecha y el usuario que lo subio")
            # queda cubierto sin columnas nuevas.
            adjunto.creado_por = adjunto.modificado_por = request.user
            adjunto.save()
            messages.success(request, 'Archivo agregado al expediente.')
            # Post/redirect/get: recargar no vuelve a subirlo.
            return redirect('consultas:adjuntos', expediente_id=expediente.pk)
    return render(request, 'consultas/adjuntos.html', {
        'expediente': expediente, 'form': form,
        'adjuntos': expediente.adjuntos.filter(activo=True).select_related('creado_por'),
    })


def adjunto_autorizado(request, adjunto_id):
    adjunto = get_object_or_404(
        Adjunto.objects.select_related('expediente'), pk=adjunto_id, activo=True)
    expediente_autorizado(request, adjunto.expediente_id)
    return adjunto


@never_cache
@xframe_options_sameorigin
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_adjunto'), raise_exception=True)
def descargar_adjunto(request, adjunto_id):
    """
    La unica puerta al archivo.

    No hay `MEDIA_URL`: nadie llega al contenido sin pasar por aqui, y aqui
    se valida sesion, permiso y que el expediente sea de una clinica del
    usuario -- igual que `ver_expediente`.

    El dia que los archivos se muevan a S3, esta vista devuelve una URL
    firmada temporal en vez del contenido. Lo que decide quien puede verlo
    sigue siendo este mismo bloque.
    """
    adjunto = adjunto_autorizado(request, adjunto_id)

    # El tipo sale de lo que se valido al subirlo, NUNCA del nombre del
    # archivo. Servir contenido ajeno con un tipo adivinado es como se
    # cuela un HTML disfrazado y se ejecuta en la sesion de la doctora.
    # `nosniff` remata: el navegador tampoco puede reinterpretarlo.
    extension = adjunto.archivo.name.rsplit('.', 1)[-1].lower()
    if adjunto.tipo == Adjunto.Tipo.PDF:
        tipo_mime = 'application/pdf'
    elif extension == 'png':
        tipo_mime = 'image/png'
    else:
        tipo_mime = 'image/jpeg'

    try:
        archivo = adjunto.archivo.open('rb')
    except FileNotFoundError:
        # La fila existe pero el archivo no esta en disco. Pasa al restaurar
        # una base sin su carpeta de archivos; mejor un 404 claro que un 500.
        raise Http404('El archivo ya no está disponible.')

    respuesta = FileResponse(archivo, content_type=tipo_mime)
    modo = 'attachment' if request.GET.get('descargar') == '1' else 'inline'
    respuesta['Content-Disposition'] = f'{modo}; filename="adjunto-{adjunto.pk}.{extension}"'
    respuesta['X-Content-Type-Options'] = 'nosniff'
    return respuesta


@require_POST
@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.change_adjunto'), raise_exception=True)
def retirar_adjunto(request, adjunto_id):
    """
    Nada se elimina (regla del proyecto): se desactiva con `activo`.

    El archivo se queda en disco a proposito. Es un expediente clinico: si
    manana hay que explicar que se subio y se retiro, el archivo tiene que
    seguir ahi. Quien lo retiro y cuando quedan en `modificado_por` y
    `fecha_modificacion`, sin nada adicional.
    """
    adjunto = adjunto_autorizado(request, adjunto_id)
    adjunto.activo = False
    adjunto.modificado_por = request.user
    adjunto.save(update_fields=['activo', 'modificado_por', 'fecha_modificacion'])
    messages.success(request, 'Archivo retirado del expediente.')
    return redirect('consultas:adjuntos', expediente_id=adjunto.expediente_id)
