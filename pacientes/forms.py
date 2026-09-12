import re
from datetime import date
from decimal import Decimal

from django import forms
from django.core.validators import RegexValidator

from .models import Contacto, Persona, calcular_edad

# Reutilizables: mismo criterio en paciente y en contacto, no se repite
# la expresion regular en cada campo.
validador_nombre = RegexValidator(
    regex=r"^[A-Za-zÁÉÍÓÚáéíóúÑñÜü]+(?:[ '\-][A-Za-zÁÉÍÓÚáéíóúÑñÜü]+)*$",
    message='Solo se permiten letras -- sin números ni caracteres especiales.',
)
validador_telefono = RegexValidator(
    regex=r'^\d{4}-\d{4}$',
    message='El teléfono debe tener el formato 0000-0000.',
)
validador_dui = RegexValidator(
    regex=r'^\d{8}-\d$',
    message='El DUI debe tener el formato 00000000-0.',
)


class RegistrarPacienteForm(forms.Form):
    """
    HU-EXP-01 (adulto) y HU-EXP-02 (menor de edad) en un solo formulario,
    con un interruptor Adulto/Menor en la pantalla -- mismo patron que ya
    tenia el mockup que se le mostro a la doctora. Una sola pantalla es
    menos que aprender para la enfermera que dos formularios separados.

    No es un ModelForm porque toca dos Personas (el paciente y el
    contacto) mas el Contacto que los relaciona -- la vista arma los
    tres registros a partir de este form.

    Si el paciente es menor o adulto **no se decide por lo que el
    interruptor mande en el POST**, sino por la fecha de nacimiento que
    de verdad se escribio (ver `clean()` mas abajo) -- el interruptor en
    pantalla es solo para mostrar los campos correctos mientras se
    escribe, nunca la fuente de verdad. Asi no hay forma de marcar
    "adulto" a proposito o por error con una fecha de nacimiento de hace
    10 anios y saltarse la exigencia de responsable.

    Contacto de referencia (adulto) es OPCIONAL (decision de Kevin,
    30/08/2026): a veces por la prisa del momento no se conoce o no da
    tiempo de tomarlo. Responsable (menor) es OBLIGATORIO (HU-EXP-02: "El
    sistema no permite guardar un menor sin responsable"). La base de
    datos no exige ninguno de los dos a nivel de tabla -- la regla vive
    solo en este formulario. Si se llena algo del contacto, se exige
    completo (o todo o nada, no a medias) en los dos casos.

    El telefono DEL PACIENTE tambien depende de si es menor o adulto
    (decision de Kevin, 05/09/2026): obligatorio para adulto (HU-EXP-01),
    opcional para menor -- un nino normalmente no tiene telefono propio,
    y HU-EXP-02 nunca lo exige, solo pide el telefono del responsable.

    Duplicados (decision de Kevin, 05/09/2026): el DUI sigue siendo
    opcional -- no se puede volver obligatorio, porque un menor de edad
    en El Salvador no tiene DUI hasta los 18 anios (lo exigiria seria
    imposible registrar a cualquier menor, HU-EXP-02 se rompe). En vez de
    eso, se valida que no exista ya alguien con el mismo DUI, y --para
    cuando no hay DUI que distinga a dos personas-- que no exista ya
    alguien con el mismo nombre completo y telefono. Aplica igual al
    paciente y a un contacto/responsable nuevo (no cuando se reutiliza
    uno existente por el buscador, eso ya es intencional).
    """

    SEXO_CHOICES = [('', 'Prefiero no decirlo'), ('F', 'Femenino'), ('M', 'Masculino')]

    # Paciente
    nombres = forms.CharField(max_length=100, label='Nombres', validators=[validador_nombre])
    apellidos = forms.CharField(max_length=100, label='Apellidos', validators=[validador_nombre])
    fecha_nacimiento = forms.DateField(
        label='Fecha de nacimiento',
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    # Obligatorio solo para adultos -- un menor de edad normalmente no
    # tiene telefono propio, y HU-EXP-02 nunca lo pide (solo pide el
    # telefono del responsable). Por eso required=False aqui: la
    # obligatoriedad real para el adulto se exige en clean(), donde ya
    # se sabe si el paciente es menor o no.
    telefono = forms.CharField(max_length=20, label='Teléfono', required=False, validators=[validador_telefono])
    dui = forms.CharField(max_length=10, label='DUI', required=False, validators=[validador_dui])
    sexo = forms.ChoiceField(choices=SEXO_CHOICES, label='Sexo', required=False)

    # Contacto de referencia, completamente opcional. Si
    # contacto_persona_id llega (se eligio una persona ya existente en
    # el buscador), se reutiliza esa Persona. Si no, y se lleno algo,
    # se crea una Persona nueva con estos datos.
    contacto_persona_id = forms.IntegerField(required=False, widget=forms.HiddenInput())
    contacto_nombres = forms.CharField(
        max_length=100, label='Nombres', required=False, validators=[validador_nombre],
    )
    contacto_apellidos = forms.CharField(
        max_length=100, label='Apellidos', required=False, validators=[validador_nombre],
    )
    contacto_telefono = forms.CharField(
        max_length=20, label='Teléfono', required=False, validators=[validador_telefono],
    )
    # Lista cerrada, no texto libre: evita "hermana"/"hrmana"/"Hermana"
    # como si fueran datos distintos. "Otro" abre contacto_parentesco_otro.
    contacto_parentesco = forms.ChoiceField(
        choices=[('', '---------')] + Contacto.Parentesco.choices,
        label='Parentesco', required=False,
    )
    contacto_parentesco_otro = forms.CharField(
        max_length=100, label='¿Cuál?', required=False, validators=[validador_nombre],
    )

    def clean_dui(self):
        # El DUI sigue siendo opcional (un menor no tiene, y un adulto a
        # veces no lo trae a mano) -- pero si SI se escribe uno, no puede
        # coincidir con el de otra Persona ya registrada. La base de
        # datos ya tiene esta regla como constraint (TEC-01), pero sin
        # este chequeo aqui el usuario veria un error tecnico feo en vez
        # de un mensaje entendible.
        dui = self.cleaned_data.get('dui')
        if dui and Persona.objects.filter(dui=dui).exists():
            raise forms.ValidationError('Ya existe una persona registrada con este DUI.')
        return dui

    def clean_fecha_nacimiento(self):
        # Sin este chequeo, una fecha futura (un tecleo de mas en el
        # anio, o un typo) produce una edad negativa mas abajo en
        # calcular_edad() -- "-1 anios" no tiene sentido para nadie y
        # ademas confunde si el paciente cuenta como menor o adulto.
        fecha = self.cleaned_data.get('fecha_nacimiento')
        if fecha and fecha > date.today():
            raise forms.ValidationError('La fecha de nacimiento no puede ser en el futuro.')
        return fecha

    def clean_contacto_persona_id(self):
        persona_id = self.cleaned_data.get('contacto_persona_id')
        if persona_id and not Persona.objects.filter(pk=persona_id).exists():
            raise forms.ValidationError('Esa persona ya no existe -- búscala de nuevo.')
        return persona_id

    def _validar_parentesco_otro(self, datos):
        if datos.get('contacto_parentesco') == Contacto.Parentesco.OTRO and not datos.get('contacto_parentesco_otro'):
            self.add_error('contacto_parentesco_otro', 'Especifica cuál es el parentesco.')

    def clean(self):
        datos = super().clean()

        # Fuente de verdad de "es menor": la fecha de nacimiento real,
        # nunca el interruptor Adulto/Menor que llega en el POST (ver
        # docstring de la clase). Si la fecha vino invalida, DateField ya
        # puso su propio error y no hay nada que calcular aqui.
        self.es_menor = False
        if datos.get('fecha_nacimiento'):
            edad = calcular_edad(datos['fecha_nacimiento'])
            self.es_menor = edad < 18

        # El telefono del paciente es obligatorio solo para adultos (ver
        # el campo arriba) -- se valida aqui, no en el campo, porque
        # depende de self.es_menor, que todavia no existe cuando Django
        # corre la validacion de cada campo por separado.
        if not self.es_menor and not datos.get('telefono'):
            self.add_error('telefono', 'El teléfono es obligatorio para pacientes adultos.')

        # Duplicado del PACIENTE por nombre + telefono -- para cuando no
        # hay DUI que lo distinga (el caso mas comun en menores, que no
        # tienen DUI). Solo compara si hay telefono: comparar dos
        # personas distintas que coincidan en nombre pero ninguna puso
        # telefono daria un falso positivo (nombres comunes son
        # frecuentes, sobre todo entre hermanos).
        if datos.get('nombres') and datos.get('apellidos') and datos.get('telefono'):
            if Persona.objects.filter(
                nombres__iexact=datos['nombres'],
                apellidos__iexact=datos['apellidos'],
                telefono=datos['telefono'],
            ).exists():
                raise forms.ValidationError(
                    f"Ya existe una persona registrada como \"{datos['nombres']} {datos['apellidos']}\" "
                    f"con el teléfono {datos['telefono']} -- verifica que no sea la misma persona."
                )

        if datos.get('contacto_persona_id'):
            # Se eligio un contacto existente: solo falta el parentesco.
            if not datos.get('contacto_parentesco'):
                self.add_error('contacto_parentesco', 'Falta el parentesco con el paciente.')
            self._validar_parentesco_otro(datos)
            return datos

        campos_contacto = ('contacto_nombres', 'contacto_apellidos', 'contacto_telefono', 'contacto_parentesco')
        llenos = [campo for campo in campos_contacto if datos.get(campo)]

        if not llenos:
            if self.es_menor:
                # HU-EXP-02: "el sistema no permite guardar un menor sin
                # responsable" -- a diferencia del adulto, aqui no se
                # puede dejar todo el bloque vacio.
                raise forms.ValidationError(
                    'Los pacientes menores de edad necesitan un responsable: '
                    'completa nombre, apellidos, teléfono y parentesco.'
                )
            # Adulto sin contacto: valido, el registro puede quedar sin el.
            return datos

        faltantes = [campo for campo in campos_contacto if not datos.get(campo)]
        if faltantes:
            mensaje = (
                'Los pacientes menores de edad necesitan un responsable con '
                'nombre, apellidos, teléfono y parentesco completos.'
                if self.es_menor else
                'Si vas a registrar un contacto de referencia, completa nombre, '
                'apellidos, teléfono y parentesco -- o deja todo el bloque vacío '
                'para omitirlo.'
            )
            raise forms.ValidationError(mensaje)

        # Mismo chequeo que arriba, ahora para el contacto/responsable
        # que se esta creando de NUEVO (no aplica si se reutilizo uno
        # existente por el buscador -- ese caso ya termino unas lineas
        # arriba, con el "return datos" del bloque contacto_persona_id).
        if Persona.objects.filter(
            nombres__iexact=datos['contacto_nombres'],
            apellidos__iexact=datos['contacto_apellidos'],
            telefono=datos['contacto_telefono'],
        ).exists():
            raise forms.ValidationError(
                f"Ya existe una persona registrada como \"{datos['contacto_nombres']} {datos['contacto_apellidos']}\" "
                f"con el teléfono {datos['contacto_telefono']} -- búscala arriba en vez de crearla de nuevo."
            )

        self._validar_parentesco_otro(datos)
        return datos


class EditarContactoForm(forms.Form):
    """
    Editar un contacto ya existente: la relacion (tipo/parentesco) Y los
    datos de la Persona (nombres/apellidos/telefono) -- decision de
    Kevin, 05/09/2026, tras evaluar restringirlo solo a la relacion.
    Sin buscador aqui: editar no es "elegir otra persona", es corregir
    los datos de la que ya esta vinculada a este Contacto.

    A diferencia de AgregarContactoForm, `contacto` (no `paciente`) es lo
    que se recibe en __init__, porque ya existe un Contacto concreto que
    editar -- de ahi se derivan tanto el paciente (para la regla de
    "Responsable" solo en menores) como la Persona a actualizar.
    """

    tipo = forms.ChoiceField(choices=Contacto.Tipo.choices, label='Tipo de relación')
    nombres = forms.CharField(max_length=100, label='Nombres', validators=[validador_nombre])
    apellidos = forms.CharField(max_length=100, label='Apellidos', validators=[validador_nombre])
    telefono = forms.CharField(max_length=20, label='Teléfono', required=False, validators=[validador_telefono])
    parentesco = forms.ChoiceField(
        choices=[('', '---------')] + Contacto.Parentesco.choices, label='Parentesco',
    )
    parentesco_otro = forms.CharField(
        max_length=100, label='¿Cuál?', required=False, validators=[validador_nombre],
    )

    def __init__(self, *args, contacto, **kwargs):
        self.contacto = contacto
        # Mismo criterio que AgregarContactoForm: "Responsable" es
        # exclusivo de menores, decidido por la edad real del paciente.
        self.es_menor = contacto.paciente.edad is not None and contacto.paciente.edad < 18
        super().__init__(*args, **kwargs)
        if not self.es_menor:
            self.fields['tipo'].widget = forms.HiddenInput()
            self.fields['tipo'].initial = Contacto.Tipo.REFERENCIA

    def _validar_parentesco_otro(self, datos):
        if datos.get('parentesco') == Contacto.Parentesco.OTRO and not datos.get('parentesco_otro'):
            self.add_error('parentesco_otro', 'Especifica cuál es el parentesco.')

    def clean(self):
        datos = super().clean()

        if not self.es_menor:
            datos['tipo'] = Contacto.Tipo.REFERENCIA

        # Mismo chequeo de duplicados que al crear, mas el exclude(): sin
        # el exclude, la propia Persona que se esta editando siempre
        # "coincidiria consigo misma" y nunca se podria guardar sin
        # cambiar nombre o telefono.
        if datos.get('nombres') and datos.get('apellidos'):
            if Persona.objects.filter(
                nombres__iexact=datos['nombres'],
                apellidos__iexact=datos['apellidos'],
                telefono=datos.get('telefono', ''),
            ).exclude(pk=self.contacto.persona_contacto_id).exists():
                raise forms.ValidationError(
                    f"Ya existe otra persona registrada como \"{datos['nombres']} {datos['apellidos']}\" "
                    f"con el teléfono {datos.get('telefono', '')}."
                )

        self._validar_parentesco_otro(datos)
        return datos

    @property
    def cambia_datos_persona(self):
        """
        True si nombres/apellidos/telefono difieren de los que ya tenia
        la Persona -- la vista lo usa solo para decidir que texto poner
        en el mensaje de exito; la confirmacion antes de enviar (porque
        esta Persona puede ser contacto de otros pacientes, o paciente
        ella misma) se hace en el navegador, en ver-expediente.js.
        """
        persona = self.contacto.persona_contacto
        datos = self.cleaned_data
        return (
            datos.get('nombres', '').strip().lower() != persona.nombres.strip().lower()
            or datos.get('apellidos', '').strip().lower() != persona.apellidos.strip().lower()
            or datos.get('telefono', '') != persona.telefono
        )


class AgregarContactoForm(forms.Form):
    """
    Agregar un contacto/responsable adicional a un paciente que YA tiene
    expediente -- la decisión que quedó pendiente desde HU-EXP-02
    ("un paciente puede tener más de un responsable") para cuando
    existiera esta pantalla (HU-EXP-05/06).

    Mismos campos y misma lógica de "buscar o crear" que el bloque de
    contacto de RegistrarPacienteForm -- la diferencia es que aquí el
    bloque completo SIEMPRE es obligatorio (el único propósito de este
    formulario es agregar uno; no existe el caso "dejarlo vacío para
    omitirlo").
    """

    tipo = forms.ChoiceField(choices=Contacto.Tipo.choices, label='Tipo de relación')
    persona_id = forms.IntegerField(required=False, widget=forms.HiddenInput())
    nombres = forms.CharField(max_length=100, label='Nombres', required=False, validators=[validador_nombre])
    apellidos = forms.CharField(max_length=100, label='Apellidos', required=False, validators=[validador_nombre])
    telefono = forms.CharField(max_length=20, label='Teléfono', required=False, validators=[validador_telefono])
    parentesco = forms.ChoiceField(
        choices=[('', '---------')] + Contacto.Parentesco.choices, label='Parentesco', required=False,
    )
    parentesco_otro = forms.CharField(
        max_length=100, label='¿Cuál?', required=False, validators=[validador_nombre],
    )

    def __init__(self, *args, paciente, **kwargs):
        # El paciente al que se le agrega el contacto -- lo necesita
        # clean() para el chequeo de "no puede ser su propio contacto" y
        # para saber contra quién comparar el Contacto ya existente.
        self.paciente = paciente
        # "Responsable" es un concepto exclusivo de menores de edad
        # (HU-EXP-02) -- un adulto solo puede tener contactos de
        # referencia. Se decide con la edad real del paciente, no con lo
        # que llegue en el POST (mismo criterio que RegistrarPacienteForm:
        # nunca confiar en el cliente para una decision de negocio).
        self.es_menor = paciente.edad is not None and paciente.edad < 18
        super().__init__(*args, **kwargs)
        if not self.es_menor:
            # Se oculta el campo en vez de quitarlo: mas simple que la
            # plantilla tenga que decidir si lo pinta o no, y clean()
            # de todas formas fuerza el valor abajo pase lo que pase en
            # el POST.
            self.fields['tipo'].widget = forms.HiddenInput()
            self.fields['tipo'].initial = Contacto.Tipo.REFERENCIA

    def clean_persona_id(self):
        persona_id = self.cleaned_data.get('persona_id')
        if persona_id and not Persona.objects.filter(pk=persona_id).exists():
            raise forms.ValidationError('Esa persona ya no existe -- búscala de nuevo.')
        return persona_id

    def _validar_parentesco_otro(self, datos):
        if datos.get('parentesco') == Contacto.Parentesco.OTRO and not datos.get('parentesco_otro'):
            self.add_error('parentesco_otro', 'Especifica cuál es el parentesco.')

    def clean(self):
        datos = super().clean()

        if not self.es_menor:
            # El campo esta oculto para un adulto, pero un POST armado a
            # mano podria mandar tipo=responsable de todas formas -- se
            # sobreescribe siempre, no solo cuando el campo se ve.
            datos['tipo'] = Contacto.Tipo.REFERENCIA

        if datos.get('persona_id'):
            # Se eligio una persona existente por el buscador: solo
            # falta el parentesco, y dos chequeos que la base de datos ya
            # exige como constraint (TEC-01) pero con un mensaje claro en
            # vez de un error tecnico si tronara la restriccion.
            if datos['persona_id'] == self.paciente.pk:
                raise forms.ValidationError('El paciente no puede ser su propio contacto.')
            if Contacto.objects.filter(paciente=self.paciente, persona_contacto_id=datos['persona_id']).exists():
                raise forms.ValidationError('Esa persona ya es contacto de este paciente.')
            if not datos.get('parentesco'):
                self.add_error('parentesco', 'Falta el parentesco con el paciente.')
            self._validar_parentesco_otro(datos)
            return datos

        # No se eligio a nadie del buscador: hay que crear una Persona
        # nueva, y a diferencia del formulario de registro, aqui el
        # bloque completo es obligatorio -- no existe "dejarlo vacio".
        campos = ('nombres', 'apellidos', 'telefono', 'parentesco')
        faltantes = [campo for campo in campos if not datos.get(campo)]
        if faltantes:
            raise forms.ValidationError(
                'Completa nombre, apellidos, teléfono y parentesco -- o búscalo arriba si ya está registrado.'
            )

        # Mismo chequeo de duplicados que RegistrarPacienteForm: sin DUI
        # que lo distinga, nombre + telefono iguales son la unica senal
        # de que podria ser la misma persona registrada dos veces.
        if Persona.objects.filter(
            nombres__iexact=datos['nombres'],
            apellidos__iexact=datos['apellidos'],
            telefono=datos['telefono'],
        ).exists():
            raise forms.ValidationError(
                f"Ya existe una persona registrada como \"{datos['nombres']} {datos['apellidos']}\" "
                f"con el teléfono {datos['telefono']} -- búscala arriba en vez de crearla de nuevo."
            )

        self._validar_parentesco_otro(datos)
        return datos


def calcular_imc(peso, talla):
    """IMC = peso(kg) / talla(m)^2, redondeado a 1 decimal. None si falta peso o talla."""
    if peso is None or not talla:
        return None
    return round(peso / (talla ** 2), 1)


class PreconsultaForm(forms.Form):
    """Signos vitales de una preconsulta, más el médico que la atenderá."""

    # Rangos de seguridad para atrapar errores de tecleo, no un limite clinico exacto.
    PRESION_SISTOLICA_MIN, PRESION_SISTOLICA_MAX = 60, 260
    PRESION_DIASTOLICA_MIN, PRESION_DIASTOLICA_MAX = 30, 150
    TALLA_MIN, TALLA_MAX = Decimal('0.30'), Decimal('2.20')
    TEMPERATURA_MIN, TEMPERATURA_MAX = Decimal('30.0'), Decimal('42.0')
    FRECUENCIA_CARDIACA_MIN, FRECUENCIA_CARDIACA_MAX = 30, 220
    SATURACION_MIN, SATURACION_MAX = 0, 100

    medico = forms.ModelChoiceField(queryset=None, label='Médico', empty_label=None)
    peso = forms.DecimalField(label='Peso (kg)', max_digits=5, decimal_places=2, min_value=0)
    talla = forms.DecimalField(
        label='Talla (metros)', max_digits=5, decimal_places=2,
        min_value=TALLA_MIN, max_value=TALLA_MAX, required=False,
        # TextInput para permitir el formato automatico del punto decimal via JS.
        widget=forms.TextInput(attrs={'placeholder': '1.20', 'inputmode': 'decimal'}),
    )
    presion_arterial = forms.CharField(
        label='Presión arterial', max_length=10, required=False,
        widget=forms.TextInput(attrs={'placeholder': '120/80', 'inputmode': 'numeric'}),
    )
    temperatura = forms.DecimalField(
        label='Temperatura (°C)', max_digits=4, decimal_places=1, required=False,
        min_value=TEMPERATURA_MIN, max_value=TEMPERATURA_MAX,
    )
    saturacion = forms.IntegerField(
        label='Saturación de oxígeno (%)', required=False,
        min_value=SATURACION_MIN, max_value=SATURACION_MAX,
    )
    frecuencia_cardiaca = forms.IntegerField(
        label='Frecuencia cardíaca (lpm)', required=False,
        min_value=FRECUENCIA_CARDIACA_MIN, max_value=FRECUENCIA_CARDIACA_MAX,
    )

    def __init__(self, *args, medicos, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['medico'].queryset = medicos
        for nombre, campo in self.fields.items():
            if nombre != 'medico':
                campo.widget.attrs.setdefault('class', 'form-control')

    def clean_presion_arterial(self):
        """Valida el formato sistólica/diastólica y sus rangos."""
        valor = self.cleaned_data.get('presion_arterial')
        if not valor:
            return valor
        coincidencia = re.match(r'^(\d{2,3})/(\d{2,3})$', valor)
        if not coincidencia:
            raise forms.ValidationError('Formato inválido -- debe ser sistólica/diastólica, ej. 120/80.')
        sistolica, diastolica = int(coincidencia.group(1)), int(coincidencia.group(2))
        if not (self.PRESION_SISTOLICA_MIN <= sistolica <= self.PRESION_SISTOLICA_MAX):
            raise forms.ValidationError(
                f'La presión sistólica debe estar entre {self.PRESION_SISTOLICA_MIN} y {self.PRESION_SISTOLICA_MAX}.'
            )
        if not (self.PRESION_DIASTOLICA_MIN <= diastolica <= self.PRESION_DIASTOLICA_MAX):
            raise forms.ValidationError(
                f'La presión diastólica debe estar entre {self.PRESION_DIASTOLICA_MIN} y {self.PRESION_DIASTOLICA_MAX}.'
            )
        return valor

    def clean(self):
        datos = super().clean()
        datos['imc'] = calcular_imc(datos.get('peso'), datos.get('talla'))
        return datos
