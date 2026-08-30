from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render

from core.models import Clinica
from core.paginacion import paginar

from .forms import RegistrarAdultoForm
from .models import Contacto, Expediente, Persona


@login_required
@permission_required('pacientes.add_persona', raise_exception=True)
def registrar_adulto(request):
    """
    HU-EXP-01. Al guardar, deja creados Persona (paciente), Persona
    (contacto, nueva o reutilizada), Contacto y Expediente -- los
    cuatro juntos o ninguno (transaction.atomic).
    """
    if request.method == 'POST':
        form = RegistrarAdultoForm(request.POST)
        if form.is_valid():
            datos = form.cleaned_data

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

                # El contacto de referencia es opcional (decision de
                # Kevin, 30/08/2026: a veces por la prisa no se conoce
                # o no da tiempo de tomarlo). Solo se crea si llego un
                # contacto existente o si se lleno el bloque completo
                # -- el form ya garantizo que no llega a medias.
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
                        tipo=Contacto.Tipo.REFERENCIA,
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
            return redirect('pacientes:registrar_adulto')
    else:
        form = RegistrarAdultoForm()

    # Si algo de la seccion de contacto vino con error, se muestra
    # abierta de una vez -- si no, el usuario no ve por que fallo.
    campos_contacto = ('contacto_nombres', 'contacto_apellidos', 'contacto_telefono', 'contacto_parentesco')
    contacto_abierto = bool(form.non_field_errors()) or any(form[campo].errors for campo in campos_contacto)

    return render(request, 'pacientes/registrar_adulto.html', {
        'form': form,
        'contacto_abierto': contacto_abierto,
    })


@login_required
@permission_required('pacientes.add_persona', raise_exception=True)
def buscar_persona(request):
    """
    Busqueda para reutilizar un contacto ya existente (HU-EXP-01: "el
    sistema permite buscar si esa persona ya existe por DUI o telefono
    y reutilizarla"). Devuelve JSON, lo consume registrar-adulto.js.

    Busca por DUI, telefono, nombres y apellidos -- estos dos ultimos
    sin importar tildes ni mayusculas ("jose" encuentra "José"), con el
    lookup `unaccent` (extension de Postgres activada en TEC-01;
    `icontains` ya resuelve las mayusculas por su cuenta).
    """
    consulta = request.GET.get('q', '').strip()
    resultados = []
    if len(consulta) >= 2:
        personas = Persona.objects.filter(
            Q(dui__icontains=consulta)
            | Q(telefono__icontains=consulta)
            | Q(nombres__unaccent__icontains=consulta)
            | Q(apellidos__unaccent__icontains=consulta)
        ).distinct().order_by('nombres')[:8]
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
    HU-EXP-04, version parcial: solo el listado, sin buscador todavia.
    El criterio completo de HU-EXP-04 pide buscar por DUI/nombre/
    telefono/DUI del responsable con resultados en vivo -- eso se agrega
    despues, junto con "seleccionar" (abrir el expediente). Por ahora es
    la version minima para ver a quienes ya se registraron.
    """
    personas = (
        Persona.objects.filter(expedientes__isnull=False)
        .distinct()
        .order_by('apellidos', 'nombres')
    )
    total = personas.count()
    pagina = paginar(personas, request)
    return render(request, 'pacientes/lista_pacientes.html', {'pagina': pagina, 'total': total})
