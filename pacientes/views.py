from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db import transaction
from django.db.models import CharField, Q, Value
from django.db.models.functions import Concat, Replace
from django.http import JsonResponse
from django.shortcuts import redirect, render

from core.models import Clinica
from core.paginacion import paginar

from .forms import RegistrarPacienteForm
from .models import Contacto, Expediente, Persona


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

    Busca por DUI, telefono, nombres, apellidos y nombre completo --
    estos ultimos sin importar tildes ni mayusculas ("jose" encuentra
    "José"), con el lookup `unaccent` (extension de Postgres activada en
    TEC-01; `icontains` ya resuelve las mayusculas por su cuenta).

    El nombre completo se compara aparte (`nombre_completo`, con
    Concat) porque nombres y apellidos son dos columnas separadas: sin
    esto, buscar "samuel manzano" no encontraba a nadie, porque esa
    cadena completa no esta contenida NI en la columna nombres NI en la
    columna apellidos por separado (una tiene "Samuel", la otra
    "Manzano") -- solo escribir una sola palabra encontraba resultados.

    DUI y telefono se guardan siempre CON guion ("0000-0000",
    "00000000-0"), pero nada obliga a que la busqueda se escriba igual
    -- de hecho es mas rapido teclear puros numeros. Por eso ademas se
    compara contra una version de la columna SIN guion
    (`dui_sin_guion`/`telefono_sin_guion`, con Replace), contra la
    misma consulta tambien sin guion: asi "12345678" y "1234-5678"
    encuentran lo mismo.
    """
    consulta = request.GET.get('q', '').strip()
    resultados = []
    if len(consulta) >= 2:
        condiciones = (
            Q(nombres__unaccent__icontains=consulta)
            | Q(apellidos__unaccent__icontains=consulta)
            | Q(nombre_completo__unaccent__icontains=consulta)
        )
        consulta_sin_guion = consulta.replace('-', '')
        if consulta_sin_guion:
            # Sin este chequeo, una busqueda de puros guiones ("--")
            # quedaria vacia despues de quitarlos, e icontains('')
            # hace match con cualquier cosa -- traeria a todo el mundo.
            condiciones |= (
                Q(dui_sin_guion__icontains=consulta_sin_guion)
                | Q(telefono_sin_guion__icontains=consulta_sin_guion)
            )

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
