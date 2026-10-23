import re

from django import forms

from pacientes.forms import SignosVitalesForm
from .models import AtencionEstetica, FichaEstetica, ProcedimientoEstetico

# Las preguntas Si/No de los antecedentes esteticos (HU-EST-02).
SI_NO = ('tratamiento_estetico', 'cirugia', 'moldeamiento_corporal', 'depilacion', 'tratamientos_faciales',
         'enfermedad', 'cirugia_medica', 'alergico', 'fracturas', 'ciclo_regular', 'anticonceptivos',
         'menopausia_andropausia', 'anestesia_previa', 'droga_recreacional')
# Las casillas sueltas de la ficha en papel.
CASILLAS = ('depilacion_laser', 'depilacion_ipl', 'botox', 'rellenos', 'prp', 'laser', 'hilos',
            'problemas_orinar', 'problemas_defecar', 'problemas_dormir', 'hace_ejercicio', 'fuma', 'alcohol')
NUMEROS = ('embarazos', 'abortos', 'partos', 'cesareas')


class FichaEsteticaForm(forms.ModelForm):
    """
    Ficha de ingreso de la paciente (HU-EST-01) y sus antecedentes
    esteticos (HU-EST-02).

    Nada es obligatorio: se preguarda mientras la doctora escribe, igual que
    la consulta, y exigir un campo ahi significaria perder lo ya escrito.
    """

    class Meta:
        model = FichaEstetica
        fields = ('estado_civil', 'religion', 'ocupacion', 'email', 'direccion',
                  'medico', 'como_conocio', 'referido_por',
                  'tratamiento_estetico', 'tratamiento_estetico_cual',
                  'cirugia', 'cirugia_cuales', 'cirugia_donde', 'cirugia_doctor',
                  'moldeamiento_corporal', 'moldeamiento_corporal_cuales',
                  'depilacion', 'depilacion_laser', 'depilacion_ipl', 'depilacion_resultado',
                  'tratamientos_faciales', 'tratamientos_faciales_cuales',
                  'botox', 'rellenos', 'prp', 'laser', 'hilos', 'otros_procedimientos',
                  'productos_en_casa',
                  'enfermedad', 'enfermedad_cuales', 'cirugia_medica', 'cirugia_medica_cual',
                  'alergico', 'alergico_a_que', 'fracturas', 'fracturas_donde',
                  'embarazos', 'abortos', 'partos', 'cesareas', 'fur', 'ciclo_regular',
                  'anticonceptivos', 'anticonceptivos_cual', 'menopausia_andropausia',
                  'anestesia_previa', 'enfermedades_familia',
                  'problemas_orinar', 'problemas_defecar', 'problemas_dormir', 'hace_ejercicio',
                  'fuma', 'alcohol', 'dieta', 'vitaminas_suplementos',
                  'droga_recreacional', 'droga_recreacional_cual', 'pastillas_para_dormir')
        labels = {
            'estado_civil': 'Estado civil',
            'religion': 'Religión',
            'ocupacion': 'Ocupación',
            'email': 'Correo electrónico',
            'direccion': 'Dirección',
            'medico': 'Médico',
            'como_conocio': '¿Cómo conoció la clínica?',
            'referido_por': '¿Quién la refirió?',
            'tratamiento_estetico': '¿Realizó o está realizando algún tratamiento médico estético?',
            'cirugia': '¿Cirugía?',
            'moldeamiento_corporal': '¿Tratamientos de reducción o moldeamiento corporal?',
            'depilacion': '¿Depilación definitiva?',
            'depilacion_laser': 'Láser',
            'depilacion_ipl': 'IPL',
            'depilacion_resultado': 'Resultado',
            'tratamientos_faciales': '¿Tratamientos faciales?',
            'botox': 'Botox',
            'rellenos': 'Rellenos',
            'prp': 'PRP',
            'laser': 'Láser',
            'hilos': 'Hilos',
            'otros_procedimientos': 'Otros',
            'productos_en_casa': '¿Qué cremas y productos utiliza en casa?',
            'enfermedad': '¿Padece alguna enfermedad?',
            'cirugia_medica': '¿Le han realizado alguna cirugía médica?',
            'alergico': '¿Es alérgico?',
            'fracturas': '¿Fracturas?',
            'embarazos': 'Embarazos',
            'abortos': 'Abortos',
            'partos': 'Partos',
            'cesareas': 'Cesáreas',
            'fur': 'FUR',
            'ciclo_regular': '¿Regular?',
            'anticonceptivos': '¿Uso de anticonceptivos?',
            'menopausia_andropausia': '¿Síntomas de menopausia o andropausia?',
            'anestesia_previa': '¿Anestesia previa?',
            'enfermedades_familia': 'Enfermedades en la familia',
            'problemas_orinar': 'Problemas al orinar',
            'problemas_defecar': 'Defecar',
            'problemas_dormir': 'Dormir',
            'hace_ejercicio': 'Ejercicio',
            'fuma': 'Fuma',
            'alcohol': 'Alcohol',
            'dieta': 'Dieta',
            'vitaminas_suplementos': 'Vitaminas o suplementos',
            'droga_recreacional': '¿Consume alguna droga recreacional?',
            'pastillas_para_dormir': '¿Pastillas para dormir?',
        }
        widgets = {
            'productos_en_casa': forms.Textarea(attrs={'rows': 2}),
            'fur': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    # Dicen QUE va, sin un valor de ejemplo que parezca ya escrito (CD-04).
    AYUDAS = {
        'tratamiento_estetico_cual': '¿Cuál?',
        'cirugia_cuales': '¿Cuáles?',
        'cirugia_donde': '¿Dónde?',
        'cirugia_doctor': 'Doctor',
        'moldeamiento_corporal_cuales': '¿Cuáles?',
        'tratamientos_faciales_cuales': '¿Cuáles?',
        'otros_procedimientos': '¿Cuáles otros?',
        'enfermedad_cuales': '¿Cuáles?',
        'cirugia_medica_cual': '¿Cuál?',
        'alergico_a_que': '¿A qué?',
        'fracturas_donde': '¿Dónde?',
        'anticonceptivos_cual': '¿Cuál?',
        'droga_recreacional_cual': '¿Cuál?',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nombre, campo in self.fields.items():
            campo.required = False
            if nombre in SI_NO:
                # Tres estados: Si, No o sin marcar (null). Sin marcar llega
                # sin la clave en el POST y el campo lo guarda como null.
                campo.widget = forms.RadioSelect(
                    choices=[(True, 'Sí'), (False, 'No')], attrs={'class': 'form-check-input'})
            elif nombre == 'depilacion_resultado':
                campo.widget = forms.RadioSelect(
                    choices=FichaEstetica.ResultadoDepilacion.choices, attrs={'class': 'form-check-input'})
            elif nombre in CASILLAS:
                campo.widget.attrs['class'] = 'form-check-input'
            elif nombre in NUMEROS:
                campo.widget.attrs.update({'class': 'form-control', 'min': 0})
            elif nombre == 'como_conocio':
                campo.widget.attrs['class'] = 'form-select'
            else:
                campo.widget.attrs['class'] = 'form-control'
            if nombre in self.AYUDAS:
                campo.widget.attrs['placeholder'] = self.AYUDAS[nombre]
        # La opcion vacia con un texto que se entienda, no el "---------" de Django.
        self.fields['como_conocio'].choices = [('', 'Sin indicar')] + list(FichaEstetica.ComoConocio.choices)


class AtencionEsteticaForm(forms.ModelForm):
    """
    Una visita de la clinica estetica (HU-EST-03). Nada es obligatorio:
    se preguarda mientras la doctora escribe, como la ficha.

    Los rangos de los signos vitales son los de la preconsulta de ProSalud:
    atrapan errores de tecleo, no son limites clinicos. Se leen de ahi para
    que una correccion valga para las dos clinicas.
    """

    LIMITES = SignosVitalesForm

    class Meta:
        model = AtencionEstetica
        fields = ('motivo', 'presion_arterial', 'frecuencia_cardiaca', 'temperatura', 'saturacion',
                  'peso', 'talla', 'figura', 'marcas', 'plan', 'rp', 'descripcion_tratamiento')
        labels = {
            'motivo': 'Motivo de la consulta',
            'presion_arterial': 'P/A',
            'frecuencia_cardiaca': 'FC (lpm)',
            'temperatura': 'TC (°C)',
            'saturacion': 'Saturación (%)',
            'peso': 'Peso (kg)',
            'talla': 'Talla (metros)',
            'plan': 'Plan',
            'rp': 'RP',
            'descripcion_tratamiento': 'Descripción del tratamiento',
            'figura': 'Figura',
            'marcas': 'Zonas a tratar',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        filas = {'motivo': 2, 'plan': 4, 'rp': 4, 'descripcion_tratamiento': 6}
        for nombre, campo in self.fields.items():
            campo.required = False
            if nombre in filas:
                campo.widget = forms.Textarea(attrs={'rows': filas[nombre]})
            campo.widget.attrs['class'] = 'form-control'
        self.fields['presion_arterial'].widget.attrs.update({'placeholder': 'Sistólica/diastólica', 'inputmode': 'numeric'})
        for nombre in ('temperatura', 'peso', 'talla'):
            self.fields[nombre].widget = forms.TextInput(attrs={'class': 'form-control', 'inputmode': 'decimal'})
        # Las zonas a tratar las dibuja marcas.js: la figura se elige con dos
        # botones y las marcas viajan como JSON en un campo oculto.
        self.fields['figura'].widget = forms.RadioSelect(
            choices=AtencionEstetica.Figura.choices,
            attrs={'class': 'btn-check', 'autocomplete': 'off', 'data-no-desmarcar': ''})
        self.fields['marcas'].widget = forms.HiddenInput()
        # Va debajo de los procedimientos, fuera del <form>, como en el papel:
        # el atributo form lo une igual al preguardado de la atencion.
        self.fields['descripcion_tratamiento'].widget.attrs['form'] = 'form-atencion'

    def clean_presion_arterial(self):
        valor = self.cleaned_data.get('presion_arterial', '').strip()
        if not valor:
            return valor
        coincidencia = re.match(r'^(\d{2,3})/(\d{2,3})$', valor)
        if not coincidencia:
            raise forms.ValidationError('Escríbala como sistólica/diastólica, con una barra en medio.')
        sistolica, diastolica = int(coincidencia.group(1)), int(coincidencia.group(2))
        if not self.LIMITES.PRESION_SISTOLICA_MIN <= sistolica <= self.LIMITES.PRESION_SISTOLICA_MAX:
            raise forms.ValidationError(
                f'La sistólica debe estar entre {self.LIMITES.PRESION_SISTOLICA_MIN} y {self.LIMITES.PRESION_SISTOLICA_MAX}.')
        if not self.LIMITES.PRESION_DIASTOLICA_MIN <= diastolica <= self.LIMITES.PRESION_DIASTOLICA_MAX:
            raise forms.ValidationError(
                f'La diastólica debe estar entre {self.LIMITES.PRESION_DIASTOLICA_MIN} y {self.LIMITES.PRESION_DIASTOLICA_MAX}.')
        return valor

    MAXIMO_MARCAS = 60
    MAXIMO_VECTORES = 12
    LARGO_NOTA = 150

    @staticmethod
    def _punto(dato):
        """Un punto de la figura: x e y en porcentaje, dentro de la imagen."""
        try:
            x, y = round(float(dato['x']), 2), round(float(dato['y']), 2)
        except (TypeError, KeyError, ValueError):
            raise forms.ValidationError('Las marcas no se pudieron leer.')
        if not (0 <= x <= 100 and 0 <= y <= 100):
            raise forms.ValidationError('Una marca quedó fuera de la figura.')
        return x, y

    def clean_marcas(self):
        """
        Puntos sobre la figura, cada uno con su nota y las flechas (vectores)
        que salen de el: [{"x", "y", "nota", "vectores": [{"x", "y"}]}].
        Se valida en el servidor aunque lo arme el navegador.
        """
        marcas = self.cleaned_data.get('marcas') or []
        if not isinstance(marcas, list) or len(marcas) > self.MAXIMO_MARCAS:
            raise forms.ValidationError('Las marcas no se pudieron leer.')
        limpias = []
        for marca in marcas:
            if not isinstance(marca, dict):
                raise forms.ValidationError('Las marcas no se pudieron leer.')
            x, y = self._punto(marca)
            nota = str(marca.get('nota', '')).strip()
            if len(nota) > self.LARGO_NOTA:
                raise forms.ValidationError(f'Cada nota puede tener hasta {self.LARGO_NOTA} letras.')
            # Las marcas anteriores a las flechas no traen la clave: sin flechas.
            vectores = marca.get('vectores') or []
            if not isinstance(vectores, list) or len(vectores) > self.MAXIMO_VECTORES:
                raise forms.ValidationError(f'Cada punto puede tener hasta {self.MAXIMO_VECTORES} flechas.')
            limpias.append({'x': x, 'y': y, 'nota': nota,
                            'vectores': [dict(zip(('x', 'y'), self._punto(v))) for v in vectores]})
        return limpias

    def _en_rango(self, nombre, minimo, maximo):
        valor = self.cleaned_data.get(nombre)
        if valor is not None and not minimo <= valor <= maximo:
            raise forms.ValidationError(f'Debe estar entre {minimo} y {maximo}.')
        return valor

    def clean_frecuencia_cardiaca(self):
        return self._en_rango('frecuencia_cardiaca', self.LIMITES.FRECUENCIA_CARDIACA_MIN,
                              self.LIMITES.FRECUENCIA_CARDIACA_MAX)

    def clean_temperatura(self):
        return self._en_rango('temperatura', self.LIMITES.TEMPERATURA_MIN, self.LIMITES.TEMPERATURA_MAX)

    def clean_saturacion(self):
        return self._en_rango('saturacion', self.LIMITES.SATURACION_MIN, self.LIMITES.SATURACION_MAX)

    def clean_talla(self):
        return self._en_rango('talla', self.LIMITES.TALLA_MIN, self.LIMITES.TALLA_MAX)

    def clean_peso(self):
        return self._en_rango('peso', 0, 300)


class ProcedimientoForm(forms.ModelForm):
    class Meta:
        model = ProcedimientoEstetico
        fields = ('nombre',)
        labels = {'nombre': 'Procedimiento'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['nombre'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Nombre del procedimiento'})

    def clean_nombre(self):
        nombre = self.cleaned_data['nombre'].strip()
        if not nombre:
            raise forms.ValidationError('Escriba el nombre del procedimiento.')
        return nombre
