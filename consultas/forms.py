from datetime import datetime, timedelta

from django import forms
from django.conf import settings
from django.utils import timezone

from .models import (Adjunto, Antecedente, Aplicacion, Consulta, ControlPosterior,
                     DetalleOrdenExamen, DetalleReceta, Incapacidad,
                     OrdenExamen, Receta, ReferenciaMedica)


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


class OrdenExamenForm(forms.Form):
    """
    Orden de examenes (HU-EXP-20), version sencilla acordada con Samuel el
    21/09/2026: solo los tipos de examen y las indicaciones.

    Los examenes se escriben separados por coma, como en el mockup
    ("Hemograma, glucosa..."), y la vista los guarda como filas de
    `DetalleOrdenExamen`. Asi la doctora escribe de corrido pero el dato
    queda estructurado para cuando exista el modulo de Laboratorio.
    """

    examenes = forms.CharField(
        label='Exámenes solicitados', max_length=1000,
        widget=forms.TextInput(attrs={'class': 'form-control',
                                      'placeholder': 'Hemograma, glucosa, orina…'}))
    indicaciones = forms.CharField(
        label='Indicaciones', required=False, max_length=1000,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2,
                                     'placeholder': 'En ayunas de 8 horas…'}))

    def clean_examenes(self):
        # "Hemograma, , glucosa," no debe crear filas vacias.
        tipos = [t.strip() for t in self.cleaned_data['examenes'].split(',') if t.strip()]
        if not tipos:
            raise forms.ValidationError('Escriba al menos un examen.')
        return tipos


class RecetaForm(forms.Form):
    """
    Receta de la consulta (HU-EXP-25).

    Un medicamento por envio, como el boton "+" del mockup: se van
    agregando a la receta de la consulta. Los tres campos son los del
    mockup y los de `DetalleReceta` -- la frecuencia va dentro de la dosis
    ("1 c/8h"), que es como lo escribe la doctora.

    Las indicaciones generales NO se piden aqui: son `Consulta.indicaciones`,
    que ya se llenan durante la atencion. Pedirlas dos veces obligaria a
    escribir lo mismo, y dejaria dos versiones del mismo dato.
    """

    medicamento = forms.CharField(
        label='Medicamento', max_length=200,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Amoxicilina 500 mg'}))
    dosis = forms.CharField(
        label='Dosis', max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '1 cápsula cada 8 horas'}))
    duracion = forms.CharField(
        label='Duración', max_length=50,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '7 días'}))

    def clean(self):
        datos = super().clean()
        for campo in ('medicamento', 'dosis', 'duracion'):
            if datos.get(campo) and not datos[campo].strip():
                self.add_error(campo, 'No puede quedar en blanco.')
        return datos


class AdjuntoForm(forms.ModelForm):
    """
    Archivo del expediente (HU-EXP-08): PDF, JPG o PNG, hasta 10 MB.

    El tipo NO se decide por la extension ni por el `content_type` que manda
    el navegador: los dos los pone quien sube el archivo. Se leen los
    primeros bytes, que es lo unico que dice de verdad que es el archivo --
    renombrar un .exe a .pdf no lo convierte en PDF.
    """

    # Los bytes con los que empieza cada formato permitido.
    FIRMAS = (
        (b'%PDF-', Adjunto.Tipo.PDF),
        (b'\xff\xd8\xff', Adjunto.Tipo.IMAGEN),          # JPG
        (b'\x89PNG\r\n\x1a\n', Adjunto.Tipo.IMAGEN),     # PNG
    )

    class Meta:
        model = Adjunto
        fields = ('archivo', 'descripcion')
        labels = {'archivo': 'Archivo', 'descripcion': 'Descripción'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['archivo'].widget.attrs.update({
            'class': 'form-control',
            # Solo filtra lo que ofrece el explorador de archivos; la
            # validacion de verdad es la de abajo.
            'accept': '.pdf,.jpg,.jpeg,.png',
        })
        self.fields['descripcion'].required = True
        self.fields['descripcion'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Ej.: Radiografía de tórax 12/09 · Examen de sangre de laboratorio externo',
        })

    def clean_descripcion(self):
        # Obligatoria aunque el modelo la deje en blanco: el nombre real del
        # archivo se descarta al guardarlo, asi que sin descripcion la lista
        # del expediente serian varias filas identicas que nadie distingue.
        descripcion = self.cleaned_data['descripcion'].strip()
        if not descripcion:
            raise forms.ValidationError('Escriba de qué es el archivo.')
        return descripcion

    def clean_archivo(self):
        archivo = self.cleaned_data['archivo']
        tope = settings.TAMANO_MAXIMO_ADJUNTO
        if archivo.size > tope:
            raise forms.ValidationError(
                f'El archivo pesa {archivo.size / 1024 / 1024:.1f} MB y el máximo '
                f'son {tope // 1024 // 1024} MB.')

        cabecera = archivo.read(8)
        archivo.seek(0)  # sin esto se guardaria el archivo sin sus primeros bytes
        for firma, tipo in self.FIRMAS:
            if cabecera.startswith(firma):
                # Se guarda aqui para que la vista no tenga que repetir la
                # deteccion: el formulario ya sabe que es.
                self.instance.tipo = tipo
                return archivo

        raise forms.ValidationError('Solo se aceptan archivos PDF, JPG o PNG.')
