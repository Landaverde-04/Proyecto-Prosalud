import re

from django import forms
from django.core.validators import MinValueValidator
from django.utils import timezone

from .models import Lote, Producto


class ProductoForm(forms.ModelForm):
    """Alta y edicion de un producto del catalogo (INV-01)."""

    class Meta:
        model = Producto
        fields = ('nombre', 'presentacion', 'unidad', 'se_vende', 'se_usa_en_clinica',
                  'stock_minimo', 'descripcion')
        labels = {
            'nombre': 'Nombre',
            'presentacion': 'Presentación',
            'unidad': 'Se cuenta por',
            'se_vende': 'Se vende',
            'se_usa_en_clinica': 'Se usa en la clínica',
            'stock_minimo': 'Existencia mínima',
            'descripcion': 'Descripción',
        }
        help_texts = {
            'presentacion': 'Opcional. Por ejemplo: bolsa de 500 ml, caja de 10 tabletas.',
            'stock_minimo': 'Cuando quede esta cantidad o menos, se marca como existencia baja.',
        }
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off'}),
            'presentacion': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off'}),
            'unidad': forms.Select(attrs={'class': 'form-select'}),
            'se_vende': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'se_usa_en_clinica': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'stock_minimo': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, clinica, **kwargs):
        super().__init__(*args, **kwargs)
        self.clinica = clinica

    @staticmethod
    def _limpiar(texto):
        return re.sub(r'\s+', ' ', texto or '').strip()

    def clean_nombre(self):
        nombre = self._limpiar(self.cleaned_data.get('nombre'))
        # Solo la primera letra: "suero fisiológico" -> "Suero fisiológico".
        return nombre[:1].upper() + nombre[1:]

    def clean_presentacion(self):
        return self._limpiar(self.cleaned_data.get('presentacion'))

    def clean(self):
        datos = super().clean()
        if not datos.get('se_vende') and not datos.get('se_usa_en_clinica'):
            raise forms.ValidationError(
                'Marca al menos un uso: que se vende, que se usa en la clínica o las dos.')

        nombre, presentacion = datos.get('nombre'), datos.get('presentacion', '')
        if nombre:
            # Se compara en Python y no con __iexact: SQLite (desarrollo) solo
            # ignora mayusculas en letras sin tilde, y "SUERO FISIOLÓGICO"
            # pasaria como distinto de "Suero fisiológico".
            buscado = (nombre.casefold(), presentacion.casefold())
            otros = (Producto.objects.filter(clinica=self.clinica).exclude(pk=self.instance.pk)
                     .values_list('nombre', 'presentacion'))
            if any((n.casefold(), p.casefold()) == buscado for n, p in otros):
                self.add_error('nombre', 'Ya existe un producto con ese nombre y esa presentación.')
        return datos


class EntradaForm(forms.ModelForm):
    """Registrar una entrada de un producto: un lote nuevo (INV-02)."""

    class Meta:
        model = Lote
        fields = ('cantidad_inicial', 'numero_lote', 'fecha_vencimiento', 'fecha_entrada', 'referencia')
        labels = {
            'cantidad_inicial': 'Cantidad que entra',
            'numero_lote': 'Número de lote',
            'fecha_vencimiento': 'Vence el',
            'fecha_entrada': 'Fecha de entrada',
            'referencia': 'Referencia',
        }
        help_texts = {
            'numero_lote': 'Opcional. El que trae la caja o el empaque.',
            'fecha_vencimiento': 'Déjalo vacío si el producto no vence.',
            'referencia': 'Opcional. Factura, proveedor o de dónde vino.',
        }
        widgets = {
            'cantidad_inicial': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'numero_lote': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off'}),
            'fecha_vencimiento': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'),
            'fecha_entrada': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'),
            'referencia': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cantidad_inicial'].min_value = 1
        self.fields['cantidad_inicial'].validators.append(MinValueValidator(1))
        if not self.is_bound:
            self.initial.setdefault('fecha_entrada', timezone.localdate())

    def clean_numero_lote(self):
        return re.sub(r'\s+', ' ', self.cleaned_data.get('numero_lote') or '').strip()

    def clean_referencia(self):
        return re.sub(r'\s+', ' ', self.cleaned_data.get('referencia') or '').strip()

    def clean_fecha_entrada(self):
        fecha = self.cleaned_data.get('fecha_entrada')
        if fecha and fecha > timezone.localdate():
            raise forms.ValidationError('La fecha de entrada no puede ser futura.')
        return fecha

    def clean_fecha_vencimiento(self):
        fecha = self.cleaned_data.get('fecha_vencimiento')
        if fecha and fecha < timezone.localdate():
            raise forms.ValidationError('Este lote ya está vencido: no se puede dar entrada.')
        return fecha
