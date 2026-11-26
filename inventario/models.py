from datetime import timedelta

from django.db import models
from django.db.models import F, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.models import Clinica, ModeloBase

# Un lote que vence dentro de estos dias se marca "por vencer".
DIAS_POR_VENCER = 30


def lotes_que_cuentan(prefijo='', hoy=None):
    """
    Condicion de los lotes que suman a la existencia: activos, con algo
    adentro y sin vencer (o que no vencen). Lo vencido sigue en su lote,
    pero ya no se puede usar ni vender.
    """
    hoy = hoy or timezone.localdate()
    return (Q(**{f'{prefijo}activo': True, f'{prefijo}cantidad_actual__gt': 0})
            & (Q(**{f'{prefijo}fecha_vencimiento__isnull': True})
               | Q(**{f'{prefijo}fecha_vencimiento__gte': hoy})))


class ProductoQuerySet(models.QuerySet):
    def con_existencia(self):
        """Agrega `existencia`: lo que hay para usar, sumando los lotes que cuentan."""
        return self.annotate(existencia=Coalesce(
            Sum('lotes__cantidad_actual', filter=lotes_que_cuentan('lotes__')), 0))

    def con_existencia_baja(self):
        """Los que tienen la existencia minima o menos (incluye los que no tienen nada)."""
        return self.con_existencia().filter(existencia__lte=F('stock_minimo'))


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

    objects = ProductoQuerySet.as_manager()

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

    def calcular_existencia(self):
        """La existencia de este producto, para cuando no viene de con_existencia()."""
        return self.lotes.filter(lotes_que_cuentan()).aggregate(
            total=Coalesce(Sum('cantidad_actual'), 0))['total']


class Lote(ModeloBase):
    """
    Cada entrada de un producto es un lote, con su vencimiento (INV-02,
    25/11/2026). Asi se sabe que vence primero y se descuenta de ahi.

    El estado (vigente, por vencer, vencido, agotado) no se guarda: se
    calcula con la fecha de hoy, para que nunca quede desactualizado.
    """

    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name='lotes')
    numero_lote = models.CharField(max_length=50, blank=True)
    # Vacio: el producto no vence (gasas, guantes...).
    fecha_vencimiento = models.DateField(null=True, blank=True)
    fecha_entrada = models.DateField(default=timezone.localdate)
    cantidad_inicial = models.PositiveIntegerField()
    cantidad_actual = models.PositiveIntegerField()
    # Factura, proveedor o de donde vino.
    referencia = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = 'Lote'
        verbose_name = 'lote'
        verbose_name_plural = 'lotes'
        # Primero lo que vence primero; lo que no vence, al final.
        ordering = [F('fecha_vencimiento').asc(nulls_last=True), 'fecha_entrada', 'pk']
        constraints = [
            models.CheckConstraint(condition=Q(cantidad_inicial__gte=1), name='lote_con_cantidad'),
        ]

    def __str__(self):
        return f'Lote {self.numero_lote or "sin número"} · {self.producto}'

    @property
    def estado(self):
        if self.cantidad_actual == 0:
            return 'agotado'
        if self.fecha_vencimiento is None:
            return 'vigente'
        hoy = timezone.localdate()
        if self.fecha_vencimiento < hoy:
            return 'vencido'
        if self.fecha_vencimiento <= hoy + timedelta(days=DIAS_POR_VENCER):
            return 'por_vencer'
        return 'vigente'

    @property
    def dias_para_vencer(self):
        if self.fecha_vencimiento is None:
            return None
        return (self.fecha_vencimiento - timezone.localdate()).days


class MovimientoInventario(ModeloBase):
    """
    Historial de todo lo que entra y sale de un lote. La cantidad lleva
    signo: positiva suma y negativa resta. Quien lo hizo es `creado_por`.
    Por ahora solo hay entradas (INV-02); las salidas, el uso en la clinica
    y los ajustes vienen despues.
    """

    class Tipo(models.TextChoices):
        ENTRADA = 'entrada', 'Entrada'
        USO_EN_CLINICA = 'uso', 'Uso en la clínica'
        SALIDA = 'salida', 'Salida'
        AJUSTE = 'ajuste', 'Ajuste'

    lote = models.ForeignKey(Lote, on_delete=models.PROTECT, related_name='movimientos')
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    cantidad = models.IntegerField()
    fecha = models.DateTimeField(default=timezone.now)
    referencia = models.CharField(max_length=100, blank=True)
    motivo = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = 'MovimientoInventario'
        verbose_name = 'movimiento de inventario'
        verbose_name_plural = 'movimientos de inventario'
        ordering = ['-fecha', '-pk']

    def __str__(self):
        return f'{self.get_tipo_display()} {self.cantidad:+d} · {self.lote}'
