from django import forms
from django.core.validators import RegexValidator

from .models import Contacto, Persona

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


class RegistrarAdultoForm(forms.Form):
    """
    HU-EXP-01: registrar paciente adulto con contacto de referencia.

    No es un ModelForm porque toca dos Personas (el paciente y el
    contacto) mas el Contacto que los relaciona -- la vista arma los
    tres registros a partir de este form.

    El contacto de referencia es OPCIONAL en el formulario (decision de
    Kevin, 30/08/2026): a veces por la prisa del momento no se conoce o
    no da tiempo de tomarlo. La base de datos no exige que exista --
    no hay ninguna restriccion a nivel de tabla que obligue un Contacto
    por Persona, asi que esto no rompe el esquema. Si se llena algo del
    contacto, se exige completo (o todo o nada, no a medias).
    """

    SEXO_CHOICES = [('', 'Prefiero no decirlo'), ('F', 'Femenino'), ('M', 'Masculino')]

    # Paciente
    nombres = forms.CharField(max_length=100, label='Nombres', validators=[validador_nombre])
    apellidos = forms.CharField(max_length=100, label='Apellidos', validators=[validador_nombre])
    fecha_nacimiento = forms.DateField(
        label='Fecha de nacimiento',
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    telefono = forms.CharField(max_length=20, label='Teléfono', validators=[validador_telefono])
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

        if datos.get('contacto_persona_id'):
            # Se eligio un contacto existente: solo falta el parentesco.
            if not datos.get('contacto_parentesco'):
                self.add_error('contacto_parentesco', 'Falta el parentesco con el paciente.')
            self._validar_parentesco_otro(datos)
            return datos

        campos_contacto = ('contacto_nombres', 'contacto_apellidos', 'contacto_telefono', 'contacto_parentesco')
        llenos = [campo for campo in campos_contacto if datos.get(campo)]

        if not llenos:
            # Nada de contacto: valido, el registro puede quedar sin el.
            return datos

        faltantes = [campo for campo in campos_contacto if not datos.get(campo)]
        if faltantes:
            raise forms.ValidationError(
                'Si vas a registrar un contacto de referencia, completa nombre, '
                'apellidos, teléfono y parentesco -- o deja todo el bloque vacío '
                'para omitirlo.'
            )
        self._validar_parentesco_otro(datos)
        return datos
