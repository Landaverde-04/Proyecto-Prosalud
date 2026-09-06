import time
import uuid
from datetime import date

from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.views.decorators.clickjacking import xframe_options_sameorigin

from core.paginacion import paginar
from pacientes.models import Expediente
from .documentos import generar_pdf
from .forms import DocumentoMedicoForm
from .models import Consulta, Incapacidad


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
    clinica = consulta.expediente.clinica
    return dict(consulta=consulta, tipo=datos['tipo'], motivo=datos['motivo'],
                dias=datos.get('dias'), fecha_inicio=datos.get('fecha_inicio'),
                fecha=timezone.localdate(), fecha_atencion=timezone.localdate(consulta.inicio),
                paciente_nombre=str(consulta.expediente.persona),
                doctor_nombre=consulta.doctor_nombre or consulta.doctor.get_full_name() or consulta.doctor.username,
                doctor_jvpm=consulta.doctor.jvpm, clinica_nombre=clinica.nombre,
                clinica_direccion=clinica.direccion, clinica_telefono=clinica.telefono)


def recuperar_previa(request, previa_id):
    dato = request.session.get('documentos_previas', {}).get(str(previa_id))
    if not dato or time.time() - dato['creada'] > 1800 or dato['campos'].get('tipo') != Incapacidad.Tipo.INCAPACIDAD:
        raise Http404('La vista previa venció. Vuelva al formulario para revisarla.')
    consulta = consulta_autorizada(request, dato['consulta_id'])
    campos = dict(dato['campos'])
    for campo in ('fecha', 'fecha_inicio', 'fecha_atencion'):
        campos[campo] = date.fromisoformat(campos[campo]) if campos[campo] else None
    return Incapacidad(consulta=consulta, solicitud_id=previa_id, **campos)


@never_cache
@login_required
@permission_required(('pacientes.view_expediente', 'consultas.view_incapacidad'), raise_exception=True)
def lista_documentos(request, expediente_id):
    expediente = expediente_autorizado(request, expediente_id)
    documentos = Incapacidad.objects.filter(consulta__expediente=expediente, activo=True).order_by('-fecha', '-pk')
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
               'inicio_opcion': 'hoy', 'fecha_inicio': timezone.localdate()}
    editar = request.GET.get('previa')
    if editar:
        try:
            anterior = recuperar_previa(request, uuid.UUID(editar))
        except ValueError:
            raise Http404
        if anterior.consulta_id != consulta.pk:
            raise Http404
        inicial.update(tipo=anterior.tipo, motivo=anterior.motivo, dias=anterior.dias,
                       inicio_opcion='personalizada' if anterior.fecha_inicio else 'hoy',
                       fecha_inicio=anterior.fecha_inicio)
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
    documento = get_object_or_404(Incapacidad.objects.select_related('consulta'), pk=documento_id, activo=True)
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
