from datetime import date

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
