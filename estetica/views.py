from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Max
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from core.clinica_activa import clinica_activa
from core.models import Clinica
from core.paginacion import es_ajax
from pacientes.models import Expediente
from .documentos import generar_pdf_atencion, generar_plantilla_atencion
from .forms import AtencionEsteticaForm, FichaEsteticaForm, ProcedimientoForm
from .models import AtencionEstetica, FichaEstetica, ProcedimientoEstetico, SesionProcedimiento


def expediente_estetico(request, expediente_id):
    """
    Expediente de la clinica estetica que este usuario puede abrir: de una
    de sus clinicas (si no, 403) y de una clinica de tipo estetica (si no,
    404: la ficha no existe para la clinica medica). Es la misma regla que
    aplica `pacientes.ver_expediente`, repetida aqui a proposito para no
    importar una funcion privada de otra app.
    """
    expediente = get_object_or_404(
        Expediente.objects.select_related('persona', 'clinica'),
        pk=expediente_id, activo=True, persona__activo=True, clinica__activo=True)
    if not request.user.clinicas.filter(pk=expediente.clinica_id).exists():
        raise PermissionDenied
    if expediente.clinica.tipo != Clinica.Tipo.ESTETICA:
        raise Http404
    return expediente


def es_de_otra_clinica(request, expediente):
    """El expediente es de una clinica del usuario, pero no de la que tiene activa."""
    activa = clinica_activa(request)
    return activa is not None and expediente.clinica_id != activa.pk


@never_cache
@login_required
@permission_required('pacientes.view_expediente', raise_exception=True)
def ficha(request, expediente_id):
    """La ficha de ingreso: la misma pantalla la crea y la corrige (HU-EST-01)."""
    expediente = expediente_estetico(request, expediente_id)
    # Con otra clinica activa, el expediente ya explica como cambiar.
    if es_de_otra_clinica(request, expediente):
        return redirect('pacientes:ver_expediente', expediente_id=expediente.pk)
    ficha = FichaEstetica.objects.filter(expediente=expediente, activo=True).first()
    return render(request, 'estetica/ficha.html', {
        'expediente': expediente, 'persona': expediente.persona,
        'ficha': ficha, 'form': FichaEsteticaForm(instance=ficha),
    })


@require_POST
@never_cache
@login_required
@permission_required('pacientes.view_expediente', raise_exception=True)
def guardar_ficha(request, expediente_id):
    """
    Preguardado de la ficha, como el de la consulta: lo que la doctora
    escribe se guarda en el servidor mientras escribe, sobre la misma fila,
    y no se pierde si recarga o cierra la ventana. La primera vez crea la
    ficha; las siguientes la corrigen.

    Sin JavaScript el formulario llega como un POST normal: se guarda igual
    y se vuelve al expediente.
    """
    expediente = expediente_estetico(request, expediente_id)
    if es_de_otra_clinica(request, expediente):
        if es_ajax(request):
            return JsonResponse({'ok': False, 'mensaje': 'Cambie a la clínica Estética para guardar esta ficha.'},
                                status=409)
        return redirect('pacientes:ver_expediente', expediente_id=expediente.pk)

    with transaction.atomic():
        ficha = (FichaEstetica.objects.select_for_update()
                 .filter(expediente=expediente, activo=True).first())
        form = FichaEsteticaForm(request.POST, instance=ficha)
        if not form.is_valid():
            if es_ajax(request):
                return JsonResponse({'ok': False, 'mensaje': f'No se guardó. {primer_error(form)}',
                                     'errores': form.errors}, status=400)
            return render(request, 'estetica/ficha.html', {
                'expediente': expediente, 'persona': expediente.persona, 'ficha': ficha, 'form': form,
            }, status=400)
        ficha = form.save(commit=False)
        ficha.expediente = expediente
        if ficha.creado_por_id is None:
            ficha.creado_por = request.user
        ficha.modificado_por = request.user
        ficha.save()

    if es_ajax(request):
        return JsonResponse({'ok': True, 'hora': timezone.localtime().strftime('%H:%M')})
    messages.success(request, 'Ficha estética guardada.')
    return redirect('pacientes:ver_expediente', expediente_id=expediente.pk)


def primer_error(form):
    """El primer error del formulario, con el nombre del campo, para el aviso del preguardado."""
    for nombre, errores in form.errors.items():
        etiqueta = form.fields[nombre].label if nombre in form.fields else ''
        return f'{etiqueta}: {errores[0]}' if etiqueta else errores[0]
    return 'Revise los datos.'


# --- Atencion de la clinica estetica (HU-EST-03) ---

def atencion_autorizada(request, atencion_id):
    """Atencion de un expediente estetico que este usuario puede ver."""
    atencion = get_object_or_404(
        AtencionEstetica.objects.select_related('expediente__persona', 'expediente__clinica', 'doctor'),
        pk=atencion_id, activo=True)
    expediente_estetico(request, atencion.expediente_id)
    return atencion


def atencion_propia(request, atencion_id):
    """
    Atencion que este usuario puede escribir: la suya, o cualquiera si
    administra el sistema. Misma regla que la consulta de ProSalud.
    """
    atencion = atencion_autorizada(request, atencion_id)
    if atencion.doctor_id != request.user.pk and not request.user.has_perm('auth.change_group'):
        raise PermissionDenied
    return atencion


def puede_escribir(usuario, atencion):
    return (not atencion.cerrada
            and (atencion.doctor_id == usuario.pk or usuario.has_perm('auth.change_group')))


def tabla_procedimientos(atencion, editable):
    """
    Los renglones de la tabla "Procedimiento | 1 ... 10" de la paciente.

    En cada renglon solo se puede marcar la siguiente sesion, y una por
    atencion; y solo se puede quitar la ultima, si se marco en esta misma
    atencion (para corregir un error, no para reescribir visitas pasadas).
    """
    renglones = []
    procedimientos = (ProcedimientoEstetico.objects.filter(expediente=atencion.expediente_id, activo=True)
                      .prefetch_related('sesiones__atencion'))
    for procedimiento in procedimientos:
        sesiones = {s.numero: s for s in procedimiento.sesiones.all() if s.activo}
        ultima = max(sesiones, default=0)
        marcada_hoy = any(s.atencion_id == atencion.pk for s in sesiones.values())
        celdas = []
        for numero in range(1, ProcedimientoEstetico.MAXIMO_SESIONES + 1):
            sesion = sesiones.get(numero)
            celdas.append({
                'numero': numero,
                'sesion': sesion,
                'puede_quitar': editable and sesion is not None and numero == ultima and sesion.atencion_id == atencion.pk,
                'puede_marcar': editable and sesion is None and numero == ultima + 1 and not marcada_hoy,
            })
        renglones.append({'procedimiento': procedimiento, 'celdas': celdas})
    return renglones


def contexto_procedimientos(request, atencion):
    editable = puede_escribir(request.user, atencion)
    return {'atencion': atencion, 'renglones': tabla_procedimientos(atencion, editable),
            'editable': editable, 'form_procedimiento': ProcedimientoForm(),
            'numeros': range(1, ProcedimientoEstetico.MAXIMO_SESIONES + 1)}


def respuesta_procedimientos(request, atencion, mensaje, tipo='success'):
    """La tabla redibujada para el fetch; sin JavaScript, vuelve a la atencion."""
    if es_ajax(request):
        return JsonResponse({
            'ok': tipo == 'success', 'mensaje': mensaje, 'tipo': tipo,
            'html': render_to_string('estetica/_procedimientos.html',
                                     contexto_procedimientos(request, atencion), request=request),
        }, status=200 if tipo == 'success' else 400)
    getattr(messages, 'success' if tipo == 'success' else 'error')(request, mensaje)
    return redirect('estetica:atencion', atencion_id=atencion.pk)


def atencion_en_curso(usuario, clinica_id, excepto_expediente):
    """Otra atencion abierta de esta doctora en esta clinica: atiende una paciente a la vez."""
    return (AtencionEstetica.objects.filter(doctor=usuario, expediente__clinica=clinica_id,
                                            cierre__isnull=True, activo=True)
            .exclude(expediente=excepto_expediente).select_related('expediente__persona').first())


@require_POST
@never_cache
@login_required
@permission_required('pacientes.view_expediente', raise_exception=True)
def nueva_atencion(request, expediente_id):
    expediente = expediente_estetico(request, expediente_id)
    if es_de_otra_clinica(request, expediente):
        return redirect('pacientes:ver_expediente', expediente_id=expediente.pk)
    with transaction.atomic():
        # Nunca dos atenciones abiertas de la misma paciente: se retoma la que hay.
        abierta = (AtencionEstetica.objects.select_for_update()
                   .filter(expediente=expediente, cierre__isnull=True, activo=True).first())
        if abierta:
            messages.info(request, 'Esta paciente ya tiene una atención sin finalizar; se retomó esa.')
            return redirect('estetica:atencion', atencion_id=abierta.pk)
        otra = atencion_en_curso(request.user, expediente.clinica_id, expediente)
        if otra:
            messages.error(request, f'Finalice la atención de {otra.expediente.persona} antes de iniciar otra.')
            return redirect('pacientes:ver_expediente', expediente_id=expediente.pk)
        atencion = AtencionEstetica.objects.create(
            expediente=expediente, doctor=request.user,
            doctor_nombre=request.user.get_full_name() or request.user.username,
            creado_por=request.user, modificado_por=request.user)
    return redirect('estetica:atencion', atencion_id=atencion.pk)


@never_cache
@login_required
@permission_required('pacientes.view_expediente', raise_exception=True)
def atencion(request, atencion_id):
    """La atencion: se escribe mientras esta abierta; finalizada, se lee."""
    atencion = atencion_autorizada(request, atencion_id)
    if es_de_otra_clinica(request, atencion.expediente):
        return redirect('pacientes:ver_expediente', expediente_id=atencion.expediente_id)
    contexto = contexto_procedimientos(request, atencion)
    # La figura sale del sexo registrado de la paciente hasta que la doctora
    # la cambie; sin sexo registrado, la de mujer, que es la mayoria.
    inicial = {}
    if not atencion.figura:
        sexo = atencion.expediente.persona.sexo
        inicial['figura'] = AtencionEstetica.Figura.HOMBRE if sexo == 'M' else AtencionEstetica.Figura.MUJER
    form = AtencionEsteticaForm(instance=atencion, initial=inicial)
    if not contexto['editable']:
        for campo in form.fields.values():
            campo.disabled = True
    contexto.update({'expediente': atencion.expediente, 'persona': atencion.expediente.persona, 'form': form})
    return render(request, 'estetica/atencion.html', contexto)


@require_POST
@never_cache
@login_required
@permission_required('pacientes.view_expediente', raise_exception=True)
def guardar_atencion(request, atencion_id):
    """Preguardado de la atencion, igual que el de la ficha."""
    atencion = atencion_propia(request, atencion_id)
    if es_de_otra_clinica(request, atencion.expediente):
        return JsonResponse({'ok': False, 'mensaje': 'Cambie a la clínica Estética para guardar esta atención.'},
                            status=409)
    with transaction.atomic():
        atencion = AtencionEstetica.objects.select_for_update().get(pk=atencion.pk)
        if atencion.cerrada:
            return JsonResponse({'ok': False, 'mensaje': 'La atención ya fue finalizada.'}, status=409)
        form = AtencionEsteticaForm(request.POST, instance=atencion)
        if not form.is_valid():
            if es_ajax(request):
                return JsonResponse({'ok': False, 'mensaje': primer_error(form), 'errores': form.errors}, status=400)
            messages.error(request, f'No se guardó. {primer_error(form)}')
            return redirect('estetica:atencion', atencion_id=atencion.pk)
        atencion = form.save(commit=False)
        atencion.modificado_por = request.user
        atencion.save()
    if es_ajax(request):
        return JsonResponse({'ok': True, 'hora': timezone.localtime().strftime('%H:%M')})
    return redirect('estetica:atencion', atencion_id=atencion.pk)


@require_POST
@never_cache
@login_required
@permission_required('pacientes.view_expediente', raise_exception=True)
def finalizar_atencion(request, atencion_id):
    atencion = atencion_propia(request, atencion_id)
    with transaction.atomic():
        atencion = AtencionEstetica.objects.select_for_update().get(pk=atencion.pk)
        if not atencion.cerrada:
            atencion.cierre = timezone.now()
            atencion.modificado_por = request.user
            atencion.save(update_fields=['cierre', 'modificado_por', 'fecha_modificacion'])
            messages.success(request, 'Atención finalizada.')
    return redirect('pacientes:ver_expediente', expediente_id=atencion.expediente_id)


@require_POST
@never_cache
@login_required
@permission_required('pacientes.view_expediente', raise_exception=True)
def agregar_procedimiento(request, atencion_id):
    atencion = atencion_propia(request, atencion_id)
    if atencion.cerrada:
        return respuesta_procedimientos(request, atencion, 'La atención ya fue finalizada.', 'danger')
    form = ProcedimientoForm(request.POST)
    if not form.is_valid():
        return respuesta_procedimientos(request, atencion, primer_error(form), 'danger')
    procedimiento = form.save(commit=False)
    procedimiento.expediente = atencion.expediente
    procedimiento.creado_por = procedimiento.modificado_por = request.user
    procedimiento.save()
    return respuesta_procedimientos(request, atencion, f'Procedimiento agregado: {procedimiento.nombre}.')


@require_POST
@never_cache
@login_required
@permission_required('pacientes.view_expediente', raise_exception=True)
def marcar_sesion(request, atencion_id, procedimiento_id):
    atencion = atencion_propia(request, atencion_id)
    with transaction.atomic():
        atencion = AtencionEstetica.objects.select_for_update().get(pk=atencion.pk)
        if atencion.cerrada:
            return respuesta_procedimientos(request, atencion, 'La atención ya fue finalizada.', 'danger')
        # Bloquea el procedimiento: dos clics seguidos no marcan dos sesiones.
        procedimiento = get_object_or_404(ProcedimientoEstetico.objects.select_for_update(),
                                          pk=procedimiento_id, expediente=atencion.expediente_id, activo=True)
        sesiones = procedimiento.sesiones.filter(activo=True)
        if sesiones.filter(atencion=atencion).exists():
            return respuesta_procedimientos(request, atencion,
                                            'Ya se marcó una sesión de este procedimiento en esta atención.', 'danger')
        siguiente = (sesiones.aggregate(ultima=Max('numero'))['ultima'] or 0) + 1
        if siguiente > ProcedimientoEstetico.MAXIMO_SESIONES:
            return respuesta_procedimientos(request, atencion,
                                            'Este procedimiento ya tiene sus diez sesiones.', 'danger')
        SesionProcedimiento.objects.create(procedimiento=procedimiento, numero=siguiente, atencion=atencion,
                                           creado_por=request.user, modificado_por=request.user)
    return respuesta_procedimientos(request, atencion, f'{procedimiento.nombre}: sesión {siguiente} marcada.')


@require_POST
@never_cache
@login_required
@permission_required('pacientes.view_expediente', raise_exception=True)
def quitar_sesion(request, atencion_id, sesion_id):
    atencion = atencion_propia(request, atencion_id)
    with transaction.atomic():
        atencion = AtencionEstetica.objects.select_for_update().get(pk=atencion.pk)
        sesion = get_object_or_404(SesionProcedimiento.objects.select_related('procedimiento'),
                                   pk=sesion_id, atencion=atencion, activo=True)
        ultima = (sesion.procedimiento.sesiones.filter(activo=True)
                  .aggregate(ultima=Max('numero'))['ultima'])
        if atencion.cerrada or sesion.numero != ultima:
            return respuesta_procedimientos(request, atencion, 'Esa sesión ya no se puede quitar.', 'danger')
        # Se retira, no se borra: queda el rastro de que se marco y se corrigio.
        sesion.activo = False
        sesion.modificado_por = request.user
        sesion.save(update_fields=['activo', 'modificado_por', 'fecha_modificacion'])
    return respuesta_procedimientos(request, atencion,
                                    f'{sesion.procedimiento.nombre}: se quitó la sesión {sesion.numero}.')


@never_cache
@login_required
@permission_required('pacientes.view_expediente', raise_exception=True)
def atenciones(request, expediente_id):
    """Historial de atenciones de la paciente en la clinica estetica."""
    expediente = expediente_estetico(request, expediente_id)
    if es_de_otra_clinica(request, expediente):
        return redirect('pacientes:ver_expediente', expediente_id=expediente.pk)
    return render(request, 'estetica/atenciones.html', {
        'expediente': expediente,
        'atenciones': expediente.atenciones_esteticas.filter(activo=True).order_by('-inicio'),
    })


@never_cache
@xframe_options_sameorigin
@login_required
@permission_required('pacientes.view_expediente', raise_exception=True)
def pdf_atencion(request, atencion_id):
    """
    La atencion en PDF, con la figura y sus marcas en una sola pagina. Se
    abre en el visor de la pantalla; ?descargar=1 baja el archivo.
    """
    atencion = atencion_autorizada(request, atencion_id)
    respuesta = HttpResponse(generar_pdf_atencion(atencion), content_type='application/pdf')
    modo = 'attachment' if request.GET.get('descargar') == '1' else 'inline'
    fecha = timezone.localtime(atencion.inicio).strftime('%Y-%m-%d')
    respuesta['Content-Disposition'] = f'{modo}; filename="atencion-estetica-{fecha}-{atencion.pk}.pdf"'
    respuesta['X-Content-Type-Options'] = 'nosniff'
    return respuesta


@never_cache
@xframe_options_sameorigin
@login_required
@permission_required('pacientes.view_expediente', raise_exception=True)
def plantilla_atencion(request, figura):
    """
    La atencion estetica en blanco, de mujer o de hombre (HU-EST-04), para
    llenarla a mano. Solo con la clinica Estetica activa. No crea registros.
    """
    clinica = clinica_activa(request)
    if clinica is None or clinica.tipo != Clinica.Tipo.ESTETICA or figura not in AtencionEstetica.Figura.values:
        raise Http404
    respuesta = HttpResponse(generar_plantilla_atencion(clinica, request.user, figura), content_type='application/pdf')
    respuesta['Content-Disposition'] = f'inline; filename="plantilla-atencion-estetica-{figura}.pdf"'
    respuesta['X-Content-Type-Options'] = 'nosniff'
    return respuesta

