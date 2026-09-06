from datetime import timedelta

from django import forms
from django.utils import timezone

from .models import Incapacidad


class DocumentoMedicoForm(forms.Form):
    motivo = forms.CharField(label='Motivo de atención o diagnóstico', max_length=5000,
                             widget=forms.Textarea(attrs={'rows': 4}))
    inicio_opcion = forms.ChoiceField(label='Inicio del reposo', required=False,
                                    choices=[('hoy', 'Hoy'), ('personalizada', 'Fecha personalizada')])
    fecha_inicio = forms.DateField(label='Fecha de inicio', required=False,
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
            datos['fecha_inicio'] = timezone.localdate()
        elif datos.get('inicio_opcion') != 'personalizada':
            self.add_error('inicio_opcion', 'Seleccione Hoy o Fecha personalizada.')
        elif not datos.get('fecha_inicio'):
            self.add_error('fecha_inicio', 'Seleccione la fecha de inicio.')
        if datos.get('fecha_inicio') and datos.get('dias'):
            try:
                datos['fecha_inicio'] + timedelta(days=datos['dias'] - 1)
            except (OverflowError, ValueError):
                self.add_error('dias', 'El período indicado excede el rango de fechas permitido.')
        return datos
