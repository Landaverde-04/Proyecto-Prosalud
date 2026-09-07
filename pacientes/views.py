from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import CharField, Exists, OuterRef, Q, Value
from django.db.models.functions import Concat, Replace
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.models import Clinica
from core.paginacion import es_ajax, paginar

from .forms import AgregarContactoForm, EditarContactoForm, RegistrarPacienteForm
from .models import Contacto, Expediente, Persona


def _condiciones_busqueda_persona(consulta):
    """
    Q de busqueda compartido por `buscar_persona` y `lista_pacientes`:
    nombre completo por PALABRAS (no la cadena completa de una sola vez)
    mas, si sobra algo despues de quitar guiones, DUI/telefono sin
    guion. Requiere que el queryset ya venga anotado con
    `nombre_completo`, `dui_sin_guion` y `telefono_sin_guion` (cada
    vista arma esas anotaciones porque ademas necesita cosas propias,
    como el DUI del responsable en `lista_pacientes`).

    Nombre completo por palabras: en El Salvador es comun tener dos
    nombres y dos apellidos (ej. "Roberto Antonio Guevara Peña"), y
    alguien que busca "roberto guevara" (saltandose el segundo nombre)
    esta escribiendo una busqueda perfectamente razonable. Comparar la
    cadena completa de una sola vez no la encuentra, porque "roberto
    guevara" nunca aparece de forma continua dentro de "roberto antonio
    guevara peña". La solucion es exigir que CADA palabra por separado
    aparezca en algun lugar del nombre completo (todas a la vez, sin
    importar el orden ni que haya otras palabras en medio) -- eso ya
    cubre tambien una sola palabra o el nombre completo exacto, sin
    necesidad de comparar nombres/apellidos por separado (nombre_completo
    ya los incluye a los dos).

    Devuelve tambien `consulta_sin_guion`, porque `lista_pacientes` la
    reutiliza para su propia condicion extra (el DUI del responsable).
    """
    condiciones = Q()
    for palabra in consulta.split():
        condiciones &= Q(nombre_completo__unaccent__icontains=palabra)

    consulta_sin_guion = consulta.replace('-', '')
    if consulta_sin_guion:
        # Sin este chequeo, una busqueda de puros guiones ("--")
        # quedaria vacia despues de quitarlos, e icontains('') hace
        # match con cualquier cosa -- traeria a todo el mundo.
        condiciones |= (
            Q(dui_sin_guion__icontains=consulta_sin_guion)
            | Q(telefono_sin_guion__icontains=consulta_sin_guion)
        )
    return condiciones, consulta_sin_guion


@login_required
@permission_required('pacientes.add_persona', raise_exception=True)
def registrar_paciente(request):
    """
    HU-EXP-01 (adulto) y HU-EXP-02 (menor de edad) en una sola vista, con
    un interruptor Adulto/Menor en la pantalla. Quien decide de verdad
    si es menor es el formulario, a partir de la fecha de nacimiento
    (ver RegistrarPacienteForm.clean() y form.es_menor) -- no el
    interruptor que llega en el POST.

    Al guardar, deja creados Persona (paciente), Persona (contacto o
    responsable, nueva o reutilizada), Contacto y Expediente -- los
    cuatro juntos o ninguno (transaction.atomic).
    """
    if request.method == 'POST':
        form = RegistrarPacienteForm(request.POST)
        if form.is_valid():
            datos = form.cleaned_data
            tipo_contacto = Contacto.Tipo.RESPONSABLE if form.es_menor else Contacto.Tipo.REFERENCIA

            with transaction.atomic():
                paciente = Persona.objects.create(
                    nombres=datos['nombres'],
                    apellidos=datos['apellidos'],
                    fecha_nacimiento=datos['fecha_nacimiento'],
                    telefono=datos['telefono'],
                    dui=datos['dui'],
                    sexo=datos['sexo'],
                    creado_por=request.user,
                    modificado_por=request.user,
                )

                # Adulto: el contacto es opcional (decision de Kevin,
                # 30/08/2026). Menor: el formulario ya garantizo que si
                # llegamos aqui, el responsable viene completo o
                # reutilizado -- nunca a medias ni vacio.
                tiene_contacto = datos['contacto_persona_id'] or datos['contacto_nombres']
                if tiene_contacto:
                    if datos['contacto_persona_id']:
                        persona_contacto = Persona.objects.get(pk=datos['contacto_persona_id'])
                    else:
                        persona_contacto = Persona.objects.create(
                            nombres=datos['contacto_nombres'],
                            apellidos=datos['contacto_apellidos'],
                            telefono=datos['contacto_telefono'],
                            creado_por=request.user,
                            modificado_por=request.user,
                        )

                    Contacto.objects.create(
                        paciente=paciente,
                        persona_contacto=persona_contacto,
                        tipo=tipo_contacto,
                        parentesco=datos['contacto_parentesco'],
                        parentesco_otro=datos['contacto_parentesco_otro'],
                        creado_por=request.user,
                        modificado_por=request.user,
                    )

                # Unica clinica que opera en la entrega de agosto.
                # get_or_create como red de seguridad si nadie ha
                # corrido sembrar_datos todavia.
                clinica, _ = Clinica.objects.get_or_create(nombre='ProSalud')
                Expediente.objects.create(
                    persona=paciente,
                    clinica=clinica,
                    creado_por=request.user,
                    modificado_por=request.user,
                )

            messages.success(request, f'Paciente {paciente} registrado correctamente.')
            # Redirige (patron post/redirect/get) en vez de reusar el
            # mismo POST: si la enfermera recarga la pagina despues de
            # guardar, no se vuelve a crear el mismo paciente. De paso
            # deja el formulario limpio y listo para el siguiente.
            return redirect('pacientes:registrar_paciente')
    else:
        form = RegistrarPacienteForm()

    # Se muestra el bloque de contacto ya expandido si: es menor (ahi es
    # obligatorio, no tiene sentido esconderlo) o si algo de esa seccion
    # vino con error -- si no, el usuario no ve por que fallo.
    campos_contacto = ('contacto_nombres', 'contacto_apellidos', 'contacto_telefono', 'contacto_parentesco')
    es_menor = getattr(form, 'es_menor', False)
    contacto_abierto = es_menor or bool(form.non_field_errors()) or any(form[campo].errors for campo in campos_contacto)

    return render(request, 'pacientes/registrar_paciente.html', {
        'form': form,
        'contacto_abierto': contacto_abierto,
        'es_menor': es_menor,
    })


@login_required
@permission_required('pacientes.add_persona', raise_exception=True)
def buscar_persona(request):
    """
    Busqueda para reutilizar un contacto ya existente (HU-EXP-01: "el
    sistema permite buscar si esa persona ya existe por DUI o telefono
    y reutilizarla"). Devuelve JSON, lo consume registrar-adulto.js.

    Busca por DUI, telefono y nombre completo -- estos ultimos sin
    importar tildes ni mayusculas ("jose" encuentra "José"), con el
    lookup `unaccent` (extension de Postgres activada en TEC-01;
    `icontains` ya resuelve las mayusculas por su cuenta). Ver
    `_condiciones_busqueda_persona` para el detalle de como se arma la
    busqueda (por palabras) y por que.
    """
    consulta = request.GET.get('q', '').strip()
    resultados = []
    if len(consulta) >= 2:
        condiciones, _ = _condiciones_busqueda_persona(consulta)

        personas = Persona.objects.annotate(
            nombre_completo=Concat('nombres', Value(' '), 'apellidos', output_field=CharField()),
            dui_sin_guion=Replace('dui', Value('-'), Value('')),
            telefono_sin_guion=Replace('telefono', Value('-'), Value('')),
        ).filter(condiciones).distinct().order_by('nombres')[:8]
        resultados = [
            {
                'id': p.id,
                'nombres': p.nombres,
                'apellidos': p.apellidos,
                'dui': p.dui,
                'telefono': p.telefono,
            }
            for p in personas
        ]
    return JsonResponse({'resultados': resultados})


@login_required
@permission_required('pacientes.view_persona', raise_exception=True)
def lista_pacientes(request):
    """
    HU-EXP-04: busca en vivo por DUI, nombre completo, telefono (con o
    sin guion) o el DUI de su contacto/responsable -- mismo patron de
    "listado sin recargar" que ya usan Usuarios/Roles/Bitacora
    (listado-vivo.js + core/paginacion.py), en vez del buscador con
    fetch/JSON que usa el cuadro de reutilizar contacto en el
    formulario de registro (son dos problemas distintos: aqui se
    navega una lista completa con paginas, alla se elige una persona
    puntual sin salir del formulario).

    Dos criterios de la historia quedan pendientes a proposito, porque
    dependen de piezas que todavia no existen:
    - "Al seleccionar un paciente se abre su expediente" -- depende de
      HU-EXP-05/06 (la pantalla del expediente). Los resultados se
      muestran pero no son clicables todavia.
    - El caso cross-clinica ("ofrece abrir expediente en la clinica
      actual") -- depende de un concepto de "clinica activa del
      usuario" que tampoco existe todavia (hoy solo opera una clinica
      real, ProSalud).
    """
    personas = (
        Persona.objects.filter(expedientes__isnull=False)
        .annotate(
            nombre_completo=Concat('nombres', Value(' '), 'apellidos', output_field=CharField()),
            dui_sin_guion=Replace('dui', Value('-'), Value('')),
            telefono_sin_guion=Replace('telefono', Value('-'), Value('')),
        )
        .prefetch_related('es_contacto_de__paciente', 'expedientes')
        .distinct()
    )

    consulta = request.GET.get('q', '').strip()
    if consulta:
        condiciones, consulta_sin_guion = _condiciones_busqueda_persona(consulta)
        if consulta_sin_guion:
            # Extra respecto a buscar_persona: aqui tambien se busca por
            # el DUI de quien acompaña al paciente. Se usa Exists() (una
            # subconsulta) en vez de anotar 'contactos__persona_contacto__dui'
            # directamente: anotar esa relacion inversa hace un JOIN que
            # multiplica la fila del paciente una vez por cada Contacto
            # que tenga (HU-EXP-05 permite mas de uno) -- .distinct() no
            # lo colapsa si el DUI difiere entre esos contactos, y el
            # paciente terminaba apareciendo repetido en la lista.
            # Exists() no se une a la consulta principal, asi que no
            # puede multiplicar filas sin importar cuantos contactos tenga.
            contacto_con_dui = Contacto.objects.filter(
                paciente=OuterRef('pk'),
            ).annotate(
                dui_sin_guion=Replace('persona_contacto__dui', Value('-'), Value('')),
            ).filter(dui_sin_guion__icontains=consulta_sin_guion)
            condiciones |= Q(Exists(contacto_con_dui))
        personas = personas.filter(condiciones)

    personas = personas.order_by('apellidos', 'nombres')
    total = personas.count()
    pagina = paginar(personas, request)

    # Si esta Persona (ademas de ser paciente) tambien es contacto de
    # otros pacientes, se le indica en la fila -- sin esto, la doctora
    # veria a "Marta" en la lista sin saber que tambien es la
    # responsable de otros dos pacientes ya registrados.
    for persona in pagina.object_list:
        persona.tambien_contacto_de = [c.paciente for c in persona.es_contacto_de.all()]
        # Hoy una Persona tiene a lo sumo un expediente real (solo opera
        # ProSalud) -- cuando exista "clinica activa del usuario" esto se
        # filtra por esa clinica en vez de tomar el primero sin mas.
        expedientes = persona.expedientes.all()
        persona.expediente_id = expedientes[0].id if expedientes else None

    contexto = {'pagina': pagina, 'consulta': consulta, 'total': total}
    plantilla = 'pacientes/resultados_pacientes.html' if es_ajax(request) else 'pacientes/lista_pacientes.html'
    return render(request, plantilla, contexto)


def _expediente_para_usuario(request, expediente_id):
    """
    Resuelve el Expediente de la URL y valida acceso -- compartido por
    `ver_expediente` y `agregar_contacto`, porque las dos vistas viven
    en la misma pantalla y deben aplicar exactamente la misma regla.

    Si el expediente no existe, 404 (normal). Si existe pero es de una
    clinica a la que el usuario no tiene acceso, 403 -- ese es el
    criterio de aceptacion explicito de HU-EXP-05. El id de la URL es
    el del Expediente, no el de la Persona: asi la verificacion es
    siempre sobre ESE expediente en concreto, sin ambiguedad si en el
    futuro una Persona tiene mas de uno (multiclinica).
    """
    expediente = get_object_or_404(
        Expediente.objects.select_related('persona', 'clinica'), pk=expediente_id,
    )
    if not request.user.clinicas.filter(pk=expediente.clinica_id).exists():
        raise PermissionDenied
    return expediente


def _tiene_responsable_activo(paciente, excluir_contacto=None):
    """
    ¿Le queda a este paciente al menos un Contacto de tipo RESPONSABLE
    activo? Mismo patron que `_hay_otro_administrador()` en seguridad:
    se usa para bloquear una accion (aqui, desactivar) que dejaria al
    paciente en un estado invalido -- un menor sin nadie responsable.
    `excluir_contacto` es el que se esta a punto de desactivar, para
    preguntar "¿le quedaria otro?" sin contar a ese mismo.
    """
    contactos = paciente.contactos.filter(tipo=Contacto.Tipo.RESPONSABLE, activo=True)
    if excluir_contacto:
        contactos = contactos.exclude(pk=excluir_contacto.pk)
    return contactos.exists()


def _contexto_ver_expediente(expediente):
    """
    Contexto completo de la pantalla del expediente -- compartido por
    `ver_expediente` (GET normal) y `agregar_contacto`/`editar_contacto`
    (cuando el formulario del modal falla y hay que volver a mostrar la
    misma pantalla con los errores, sin perder el resto del contenido).
    """
    persona = expediente.persona
    # "Responsable" es exclusivo de menores (HU-EXP-02) -- lo usan los
    # modales de agregar/editar contacto para decidir si muestran el
    # desplegable de tipo o lo fuerzan a "referencia". Es un dato de la
    # PANTALLA completa (todos sus contactos comparten el mismo
    # paciente), no de cada Contacto por separado.
    es_menor = persona.edad is not None and persona.edad < 18

    # HU-EXP-05 pide que la cabecera muestre los antecedentes del paciente.
    # Se leen por la relacion inversa (`Antecedente.expediente`, HU-EXP-07),
    # sin importar el modelo de `consultas` aqui.
    antecedentes = expediente.antecedentes.filter(activo=True)

    # "DUI o datos del responsable" (HU-EXP-05): si no tiene DUI propio
    # (tipico de un menor, aunque tambien puede faltarle a un adulto,
    # ver reglas de negocio), se muestra a su responsable en su lugar.
    # Es el PRIMER responsable ACTIVO encontrado -- un resumen rapido
    # para la cabecera, no la lista completa (esa vive en 'contactos').
    responsable = None
    if not persona.dui:
        contacto_responsable = (
            persona.contactos
            .filter(tipo=Contacto.Tipo.RESPONSABLE, activo=True)
            .select_related('persona_contacto')
            .first()
        )
        if contacto_responsable:
            responsable = contacto_responsable.persona_contacto

    return {
        'expediente': expediente,
        'persona': persona,
        'es_menor': es_menor,
        'responsable': responsable,
        'antecedentes': antecedentes,
        # Todos los contactos ACTIVOS del paciente (HU-EXP-02: "un
        # paciente puede tener mas de uno") -- a diferencia de
        # 'responsable' arriba, esta lista es la que se administra desde
        # los botones "Agregar"/"Editar"/"Desactivar". Uno desactivado
        # nunca se elimina (regla del proyecto), solo deja de listarse
        # aqui -- no hay pantalla de "reactivar" todavia.
        'contactos': (
            persona.contactos.filter(activo=True)
            .select_related('persona_contacto')
            .order_by('-tipo', 'persona_contacto__nombres')
        ),
        'agregar_contacto_form': AgregarContactoForm(paciente=persona),
        'abrir_modal_contacto': False,
        # Formulario y bandera del modal COMPARTIDO de editar -- solo se
        # llenan de verdad cuando `editar_contacto` falla y hay que
        # reabrirlo con sus errores (ver esa vista mas abajo).
        'editar_contacto_form': None,
        'editar_contacto_id': None,
    }


@login_required
@permission_required('pacientes.view_expediente', raise_exception=True)
def ver_expediente(request, expediente_id):
    """
    HU-EXP-05 (cabecera con datos preclinicos) y HU-EXP-06 (panel de
    tarjetas estilo Dr. SV) en una sola vista: el panel se muestra
    debajo de la cabecera, en la misma pantalla.

    Solo quien tiene el permiso 'pacientes.view_expediente' llega aqui
    -- ese permiso se otorga desde Roles solo a Doctor/Doctora
    Administradora, nunca a Enfermera (regla de negocio: "Solo los
    doctores pueden abrir el expediente completo").
    """
    expediente = _expediente_para_usuario(request, expediente_id)
    return render(request, 'pacientes/ver_expediente.html', _contexto_ver_expediente(expediente))


@require_POST
@login_required
@permission_required('pacientes.view_expediente', raise_exception=True)
def agregar_contacto(request, expediente_id):
    """
    Agregar un contacto/responsable adicional a un paciente que ya tiene
    expediente -- pendiente desde HU-EXP-02, resuelto aqui como una
    accion sobre el expediente ya abierto (ver decision en
    HU-EXP-02.md). Solo acepta POST: el modal que lo dispara vive dentro
    de `ver_expediente.html`, no hay ninguna pantalla propia para GET.

    Mismo permiso que `ver_expediente` (no 'add_persona'): esta accion
    vive dentro del expediente, asi que el permiso que importa es poder
    abrir el expediente, no el de registrar pacientes nuevos -- son dos
    puntos de entrada distintos a la misma regla de negocio (solo
    doctores administran el expediente completo).
    """
    expediente = _expediente_para_usuario(request, expediente_id)
    paciente = expediente.persona

    form = AgregarContactoForm(request.POST, paciente=paciente)
    if form.is_valid():
        datos = form.cleaned_data
        with transaction.atomic():
            if datos['persona_id']:
                persona_contacto = Persona.objects.get(pk=datos['persona_id'])
            else:
                persona_contacto = Persona.objects.create(
                    nombres=datos['nombres'],
                    apellidos=datos['apellidos'],
                    telefono=datos['telefono'],
                    creado_por=request.user,
                    modificado_por=request.user,
                )
            Contacto.objects.create(
                paciente=paciente,
                persona_contacto=persona_contacto,
                tipo=datos['tipo'],
                parentesco=datos['parentesco'],
                parentesco_otro=datos['parentesco_otro'],
                creado_por=request.user,
                modificado_por=request.user,
            )
        messages.success(request, f'{persona_contacto} agregado como contacto de {paciente}.')
        # Post/redirect/get, igual que registrar_paciente: evita volver a
        # crear el mismo contacto si se recarga la pagina despues.
        return redirect('pacientes:ver_expediente', expediente_id=expediente.id)

    # Formulario invalido: se vuelve a mostrar la MISMA pantalla del
    # expediente (no una pagina propia del modal), con el formulario ya
    # enviado (y sus errores) en vez de uno en blanco, y una senal para
    # que la plantilla abra el modal solo -- si no, los errores quedarian
    # escondidos detras de un modal cerrado.
    contexto = _contexto_ver_expediente(expediente)
    contexto['agregar_contacto_form'] = form
    contexto['abrir_modal_contacto'] = True
    return render(request, 'pacientes/ver_expediente.html', contexto)


@require_POST
@login_required
@permission_required('pacientes.view_expediente', raise_exception=True)
def editar_contacto(request, expediente_id, contacto_id):
    """
    Editar un contacto ya existente del paciente -- tanto la relacion
    (tipo/parentesco) como los datos de la Persona (nombres/apellidos/
    telefono). Decision de Kevin (05/09/2026): se permite editar todo,
    con una confirmacion extra en el navegador si nombre o telefono
    cambian (ver ver-expediente.js) -- esa misma Persona puede ser
    contacto de otros pacientes, o paciente ella misma, y el cambio se
    reflejaria ahi tambien.

    `contacto_id` se filtra por `paciente=expediente.persona`, no solo
    por su propio id: sin esto, alguien con acceso a ESTE expediente
    podria editar el Contacto de OTRO paciente con solo cambiar el
    numero en la URL (IDOR) -- el permiso 'view_expediente' certifica
    que puede administrar ESTE expediente, no cualquier Contacto del
    sistema.
    """
    expediente = _expediente_para_usuario(request, expediente_id)
    contacto = get_object_or_404(
        Contacto.objects.select_related('persona_contacto'),
        pk=contacto_id, paciente=expediente.persona, activo=True,
    )

    form = EditarContactoForm(request.POST, contacto=contacto)
    if form.is_valid():
        datos = form.cleaned_data
        cambia_persona = form.cambia_datos_persona
        with transaction.atomic():
            persona_contacto = contacto.persona_contacto
            persona_contacto.nombres = datos['nombres']
            persona_contacto.apellidos = datos['apellidos']
            persona_contacto.telefono = datos['telefono']
            persona_contacto.modificado_por = request.user
            persona_contacto.save()

            contacto.tipo = datos['tipo']
            contacto.parentesco = datos['parentesco']
            contacto.parentesco_otro = datos['parentesco_otro']
            contacto.modificado_por = request.user
            contacto.save()

        mensaje = f'Contacto de {expediente.persona} actualizado.'
        if cambia_persona:
            mensaje += ' Como esta persona puede estar vinculada a otros pacientes, el cambio se ve ahí también.'
        messages.success(request, mensaje)
        return redirect('pacientes:ver_expediente', expediente_id=expediente.id)

    # Igual que agregar_contacto: se vuelve a mostrar la misma pantalla
    # completa, con el formulario y sus errores, señalando CUAL de los
    # contactos (puede haber varios) es el que fallo.
    contexto = _contexto_ver_expediente(expediente)
    contexto['editar_contacto_form'] = form
    contexto['editar_contacto_id'] = contacto.id
    return render(request, 'pacientes/ver_expediente.html', contexto)


@require_POST
@login_required
@permission_required('pacientes.view_expediente', raise_exception=True)
def desactivar_contacto(request, expediente_id, contacto_id):
    """
    "Eliminar" un contacto -- en realidad se desactiva (regla del
    proyecto: nada se elimina, ver ModeloBase.activo), igual que ya
    pasa con Usuario.is_active. Nunca se borra el registro: conserva el
    historial de quien fue responsable/contacto de este paciente.

    Guarda para menores (mismo patron que la guarda del ultimo
    administrador en seguridad): un menor SIEMPRE necesita al menos un
    responsable activo (HU-EXP-02), asi que no se puede desactivar el
    ultimo. Un adulto no tiene esa restriccion -- sus contactos de
    referencia siempre fueron opcionales.
    """
    expediente = _expediente_para_usuario(request, expediente_id)
    paciente = expediente.persona
    contacto = get_object_or_404(Contacto, pk=contacto_id, paciente=paciente, activo=True)

    es_menor = paciente.edad is not None and paciente.edad < 18
    si_ultimo_responsable = (
        es_menor
        and contacto.tipo == Contacto.Tipo.RESPONSABLE
        and not _tiene_responsable_activo(paciente, excluir_contacto=contacto)
    )
    if si_ultimo_responsable:
        messages.error(
            request,
            f'{contacto.persona_contacto} es el único responsable de {paciente}. '
            'Agrega otro responsable antes de desactivar este, o el paciente quedaría sin ninguno.',
        )
    else:
        contacto.activo = False
        contacto.modificado_por = request.user
        contacto.save()
        messages.success(request, f'{contacto.persona_contacto} ya no es contacto de {paciente}.')

    return redirect('pacientes:ver_expediente', expediente_id=expediente.id)
