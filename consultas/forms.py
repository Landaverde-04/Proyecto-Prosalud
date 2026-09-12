from datetime import datetime, timedelta

from django import forms
from django.utils import timezone

from .models import (Antecedente, Aplicacion, Consulta, ControlPosterior, Incapacidad,
                     ReferenciaMedica)


class DocumentoMedicoForm(forms.Form):
    motivo = forms.CharField(label='Motivo de atención o diagnóstico', max_length=5000,
                             widget=forms.Textarea(attrs={'rows': 4}))
    inicio_opcion = forms.ChoiceField(label='Inicio del reposo', required=False,
                                    choices=[('hoy', 'Hoy'), ('personalizada', 'Fecha personalizada')])
    fecha_inicio_incapacidad = forms.DateField(label='Fecha de inicio', required=False,
                                  widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    dias = forms.IntegerField(label='Días de reposo', min_value=1, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs['class'] = 'form-select' if isinstance(campo.widget, forms.Select) else 'form-control'

    def clean(self):
        datos = super().clean()
        datos['tipo'] = Incapacidad.Tipo.INCAPACIDAD
        if not datos.get('dias'):
            self.add_error('dias', 'Indique la cantidad de días de reposo.')
        if datos.get('inicio_opcion') == 'hoy':
            datos['fecha_inicio_incapacidad'] = timezone.localdate()
        elif datos.get('inicio_opcion') != 'personalizada':
            self.add_error('inicio_opcion', 'Seleccione Hoy o Fecha personalizada.')
        elif not datos.get('fecha_inicio_incapacidad'):
            self.add_error('fecha_inicio_incapacidad', 'Seleccione la fecha de inicio.')
        if datos.get('fecha_inicio_incapacidad') and datos.get('dias'):
            try:
                datos['fecha_inicio_incapacidad'] + timedelta(days=datos['dias'] - 1)
            except (OverflowError, ValueError):
                self.add_error('dias', 'El período indicado excede el rango de fechas permitido.')
        return datos


class ConsultaClinicaForm(forms.ModelForm):
    """
    Los campos que se llenan en cada atencion (HU-EXP-17).

    NO incluye `antecedentes` ni `alergias`, aunque la tabla tenga esas dos
    columnas desde TEC-01: son datos del paciente, no de una visita. Viven
    en su expediente (HU-EXP-07) y se consultan desde ahi. Preguntarlos en
    cada consulta obliga a reescribir lo mismo cada vez, y si un dia no se
    escriben, esa consulta parece decir que el paciente no tiene alergias.
    El mockup que aprobo la doctora tampoco los incluye aqui.

    Con `borrador=True` nada es obligatorio: es el formulario que usa el
    preguardado automatico mientras la doctora escribe, y ahi exigir algo
    significaria perder lo que ya lleva escrito. La validacion completa
    corre al finalizar la consulta, no antes.
    """

    class Meta:
        model = Consulta
        fields = ('motivo', 'historia_enfermedad_actual', 'examen_fisico',
                  'diagnostico', 'tratamiento', 'indicaciones')
        labels = {
            'motivo': 'Motivo de consulta',
            'historia_enfermedad_actual': 'Historia de la enfermedad actual',
            'examen_fisico': 'Examen físico',
            'diagnostico': 'Diagnóstico',
            'tratamiento': 'Tratamiento',
            'indicaciones': 'Indicaciones',
        }

    def __init__(self, *args, borrador=False, **kwargs):
        super().__init__(*args, **kwargs)
        for nombre, campo in self.fields.items():
            campo.widget = forms.Textarea(attrs={
                'class': 'form-control', 'rows': 4 if nombre == 'motivo' else 3,
            })
            if borrador:
                campo.required = False


class ConsultaManualForm(forms.Form):
    """
    Registro manual de una atencion que ya ocurrio: la doctora dicta la
    fecha y la hora reales (HU-EXP-17). Cuando exista la cola de consulta
    (HU-EXP-12), la fila llegara ya creada y este formulario no se usa --
    ahi el inicio lo marca el boton "Iniciar consulta".
    """

    fecha = forms.DateField(label='Fecha de la atención',
                            widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    hora = forms.TimeField(label='Hora de la atención',
                           widget=forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs['class'] = 'form-control'

    def clean(self):
        datos = super().clean()
        if datos.get('fecha') and datos.get('hora'):
            inicio = timezone.make_aware(datetime.combine(datos['fecha'], datos['hora']))
            if inicio > timezone.localtime():
                raise forms.ValidationError('La atención no puede quedar registrada en el futuro.')
            datos['inicio'] = inicio
        return datos


class AntecedenteForm(forms.ModelForm):
    """Antecedente del paciente (HU-EXP-07): tipo de lista cerrada + detalle."""

    class Meta:
        model = Antecedente
        fields = ('tipo', 'detalle')
        labels = {'tipo': 'Tipo de antecedente', 'detalle': 'Detalle'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tipo'].widget.attrs['class'] = 'form-select'
        self.fields['detalle'].widget = forms.Textarea(attrs={
            'class': 'form-control', 'rows': 2,
            'placeholder': 'Ej.: Penicilina · Diabetes tipo 2 desde 2019 · Apendicectomía 2015',
        })

    def clean_detalle(self):
        detalle = self.cleaned_data['detalle'].strip()
        if not detalle:
            raise forms.ValidationError('Escriba el detalle del antecedente.')
        return detalle


class ReferenciaMedicaForm(forms.ModelForm):
    """
    Referencia a un especialista (HU-EXP-23).

    `especialidad` es texto libre por decision de Samuel (06/09/2026): no
    tiene sentido cargar un catalogo mundial de especialidades para usar
    cinco. Tampoco lleva destinatario: la referencia es una recomendacion
    abierta que el paciente lleva a donde decida, no un documento dirigido.
    """

    class Meta:
        model = ReferenciaMedica
        fields = ('especialidad', 'motivo', 'observaciones')
        labels = {'especialidad': 'Especialidad', 'motivo': 'Motivo de la referencia',
                  'observaciones': 'Observaciones'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['especialidad'].widget = forms.TextInput(attrs={
            'class': 'form-control', 'placeholder': 'Cardiología, Dermatología…'})
        for nombre in ('motivo', 'observaciones'):
            self.fields[nombre].widget = forms.Textarea(attrs={'class': 'form-control', 'rows': 2})
        self.fields['observaciones'].required = False

    def clean_especialidad(self):
        especialidad = self.cleaned_data['especialidad'].strip()
        if not especialidad:
            raise forms.ValidationError('Indique la especialidad.')
        return especialidad


class ControlPosteriorForm(forms.ModelForm):
    """
    Control posterior programado desde la consulta (HU-EXP-24).

    Sin hora: el criterio pide solo la fecha. El estado no se elige al
    programarlo -- nace `pendiente` y se cambia despues desde el listado.
    """

    class Meta:
        model = ControlPosterior
        fields = ('fecha_control', 'motivo')
        labels = {'fecha_control': 'Fecha del control', 'motivo': 'Motivo del control'}
        widgets = {'fecha_control': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fecha_control'].widget.attrs['class'] = 'form-control'
        self.fields['motivo'].widget = forms.Textarea(attrs={'class': 'form-control', 'rows': 2})

    def clean_fecha_control(self):
        fecha = self.cleaned_data['fecha_control']
        # Un control se programa hacia adelante; en el pasado no es un control.
        if fecha < timezone.localdate():
            raise forms.ValidationError('El control no puede programarse en una fecha pasada.')
        return fecha


class ReprogramarControlForm(forms.ModelForm):
    """Solo la fecha: reprogramar es mover el control, no reescribirlo."""

    class Meta:
        model = ControlPosterior
        fields = ('fecha_control',)
        labels = {'fecha_control': 'Nueva fecha'}
        widgets = {'fecha_control': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'},
                                                    format='%Y-%m-%d')}

    clean_fecha_control = ControlPosteriorForm.clean_fecha_control


class AplicacionForm(forms.ModelForm):
    """
    Aplicacion o servicio indicado en la consulta (HU-EXP-21): suero,
    curacion, nebulizacion u otro.

    No incluye `ejecutada` ni sus dos campos: la doctora la indica, y quien
    la aplica la marca despues. Son dos momentos distintos.
    """

    class Meta:
        model = Aplicacion
        fields = ('tipo', 'dosis', 'indicaciones')
        labels = {'tipo': 'Tipo', 'dosis': 'Dosis', 'indicaciones': 'Indicaciones'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tipo'].widget.attrs['class'] = 'form-select'
        self.fields['dosis'].widget = forms.TextInput(attrs={
            'class': 'form-control', 'placeholder': '500 ml, 2 puff…'})
        self.fields['indicaciones'].widget = forms.Textarea(attrs={'class': 'form-control', 'rows': 2})
