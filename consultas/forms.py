from datetime import datetime, timedelta

from django import forms
from django.utils import timezone

from .models import Antecedente, Consulta, Incapacidad


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
