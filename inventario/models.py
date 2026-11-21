from django.db import models
from django.db.models import Q

from core.models import Clinica, ModeloBase


class Producto(ModeloBase):
    """
    Lo que la clinica tiene en existencia (INV-01, 20/11/2026). Un mismo
    producto puede venderse y tambien usarse en la clinica (una crema, por
    ejemplo): por eso son dos casillas y no un tipo, y la existencia es una
    sola para los dos usos.

    El inventario solo se usa en la clinica medica (Clinica.usa_inventario),
    pero cada producto guarda su clinica, igual que los expedientes, por si
    otra lo necesita despues.
    """

    class Unidad(models.TextChoices):
        UNIDAD = 'unidad', 'Unidad'
        CAJA = 'caja', 'Caja'
        FRASCO = 'frasco', 'Frasco'
        AMPOLLA = 'ampolla', 'Ampolla'
        BOLSA = 'bolsa', 'Bolsa'
        TUBO = 'tubo', 'Tubo'
        SOBRE = 'sobre', 'Sobre'
        PAR = 'par', 'Par'
        OTRO = 'otro', 'Otro'

    clinica = models.ForeignKey(Clinica, on_delete=models.PROTECT, related_name='productos')
    nombre = models.CharField(max_length=150)
    presentacion = models.CharField(max_length=100, blank=True)
    unidad = models.CharField(max_length=15, choices=Unidad.choices, default=Unidad.UNIDAD)
    se_vende = models.BooleanField(default=False)
    se_usa_en_clinica = models.BooleanField(default=True)
    stock_minimo = models.PositiveIntegerField(default=0)
    descripcion = models.TextField(blank=True)

    class Meta:
        db_table = 'Producto'
        verbose_name = 'producto'
        verbose_name_plural = 'productos'
        ordering = ['nombre', 'presentacion']
        constraints = [
            models.UniqueConstraint(
                fields=['clinica', 'nombre', 'presentacion'], name='producto_unico_en_la_clinica'),
            models.CheckConstraint(
                condition=Q(se_vende=True) | Q(se_usa_en_clinica=True), name='producto_con_algun_uso'),
        ]

    def __str__(self):
        return f'{self.nombre} · {self.presentacion}' if self.presentacion else self.nombre

    @property
    def usos(self):
        """Etiquetas para la lista: de venta, insumo o las dos."""
        etiquetas = []
        if self.se_vende:
            etiquetas.append('De venta')
        if self.se_usa_en_clinica:
            etiquetas.append('Insumo')
        return etiquetas
