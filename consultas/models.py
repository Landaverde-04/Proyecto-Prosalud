from django.conf import settings
from django.db import models

from core.models import ModeloBase
from pacientes.models import Expediente, Persona


class Consulta(ModeloBase):
    """
    Cuelga de Expediente, no de Persona directamente: asi obtiene su
    clinica del expediente al que pertenece, sin guardarla por separado
    (TEC-01) -- ver la propiedad `clinica` mas abajo.

    Los campos de la Cola de Consulta (es_emergencia, hora_llegada,
    motivo_prioridad, nota_retiro) NO estan todavia: la Cola es
    HU-EXP-12 a HU-EXP-16, agendada despues de la entrega de agosto.
    Se agregan con esas historias, via una migracion nueva.
    """

    expediente = models.ForeignKey(
        Expediente, on_delete=models.PROTECT, related_name='consultas',
    )
    # PROTECT, no el CASCADE por defecto de Django: un doctor con
    # historial no debe poder eliminarse aunque alguien encuentre la
    # forma de intentarlo.
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='consultas_atendidas',
    )
    # Nombre del doctor congelado al crear la consulta -- si el doctor
    # edita su perfil despues, esta consulta no debe cambiar de nombre.
    # Se llena una sola vez en la vista, nunca se vuelve a actualizar.
    doctor_nombre = models.CharField(max_length=150, blank=True)

    inicio = models.DateTimeField(auto_now_add=True)
    cierre = models.DateTimeField(null=True, blank=True)

    motivo = models.TextField()
    historia_enfermedad_actual = models.TextField(blank=True)
    antecedentes = models.TextField(blank=True)
    alergias = models.TextField(blank=True)
    examen_fisico = models.TextField(blank=True)
    diagnostico = models.TextField(blank=True)
    tratamiento = models.TextField(blank=True)
    indicaciones = models.TextField(blank=True)

    class Meta:
        db_table = 'Consulta'
        verbose_name = 'consulta'
        verbose_name_plural = 'consultas'
        ordering = ['-inicio']

    def __str__(self):
        return f'Consulta de {self.expediente.persona} · {self.inicio:%d/%m/%Y}'

    @property
    def clinica(self):
        return self.expediente.clinica


class SignosVitales(ModeloBase):
    """
    Uno a uno con Consulta: al guardar los signos vitales, el sistema
    crea la consulta (HU-EXP-09) -- pero una consulta puede existir sin
    ellos (Escenario B, fuera de horario). Por eso vive en `consultas/`
    y no en `pacientes/`: si viviera alla, pacientes dependeria de
    consultas y consultas de pacientes al mismo tiempo (dependencia
    circular entre apps). La historia (HU-EXP-09/10/11) sigue siendo de
    Kevin -- solo el archivo del modelo vive aqui.
    """

    consulta = models.OneToOneField(
        Consulta, on_delete=models.PROTECT, related_name='signos_vitales',
    )
    tomado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='signos_vitales_tomados',
    )

    peso = models.DecimalField(max_digits=5, decimal_places=2)
    # Solo se registra en menores de edad (HU-EXP-09).
    talla = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    # Solo adultos y adultos mayores.
    presion_arterial = models.CharField(max_length=10, blank=True)
    temperatura = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    # Solo en emergencias.
    saturacion = models.IntegerField(null=True, blank=True)
    # Opcional: la clinica medica no la usa, la estetica si.
    frecuencia_cardiaca = models.IntegerField(null=True, blank=True)
    # Calculado a partir de peso/talla y guardado junto con la
    # preconsulta (HU-EXP-10) -- queda vacio si no hay talla.
    imc = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)

    class Meta:
        db_table = 'SignosVitales'
        verbose_name = 'signos vitales'
        verbose_name_plural = 'signos vitales'

    def __str__(self):
        return f'Signos vitales · {self.consulta}'


class Receta(ModeloBase):
    """Uno a uno con Consulta (TEC-01): al emitirla, la consulta se cierra."""

    consulta = models.OneToOneField(
        Consulta, on_delete=models.PROTECT, related_name='receta',
    )
    doctor_nombre = models.CharField(max_length=150, blank=True)
    folio = models.CharField(max_length=20, unique=True)
    fecha = models.DateField(auto_now_add=True)

    class Meta:
        db_table = 'Receta'
        verbose_name = 'receta'
        verbose_name_plural = 'recetas'

    def __str__(self):
        return f'Receta {self.folio}'


class DetalleReceta(ModeloBase):
    receta = models.ForeignKey(
        Receta, on_delete=models.PROTECT, related_name='detalles',
    )
    medicamento = models.CharField(max_length=200)
    dosis = models.CharField(max_length=100)
    duracion = models.CharField(max_length=50)

    class Meta:
        db_table = 'DetalleReceta'
        verbose_name = 'detalle de receta'
        verbose_name_plural = 'detalles de receta'

    def __str__(self):
        return f'{self.medicamento} · {self.receta.folio}'


class Incapacidad(ModeloBase):
    """Incapacidad o constancia medica -- un mismo modelo con `tipo` (HU-EXP-22)."""

    class Tipo(models.TextChoices):
        INCAPACIDAD = 'incapacidad', 'Incapacidad'
        CONSTANCIA = 'constancia', 'Constancia médica'

    consulta = models.ForeignKey(
        Consulta, on_delete=models.PROTECT, related_name='incapacidades',
    )
    doctor_nombre = models.CharField(max_length=150, blank=True)
    tipo = models.CharField(max_length=15, choices=Tipo.choices)
    folio = models.CharField(max_length=20)
    fecha = models.DateField(auto_now_add=True)
    # Solo aplica cuando tipo es INCAPACIDAD; una constancia no lleva dias.
    dias = models.IntegerField(null=True, blank=True)
    motivo = models.TextField()

    class Meta:
        db_table = 'Incapacidad'
        verbose_name = 'incapacidad o constancia'
        verbose_name_plural = 'incapacidades y constancias'

    def __str__(self):
        return f'{self.get_tipo_display()} {self.folio}'


class ReferenciaMedica(ModeloBase):
    consulta = models.ForeignKey(
        Consulta, on_delete=models.PROTECT, related_name='referencias',
    )
    doctor_nombre = models.CharField(max_length=150, blank=True)
    fecha = models.DateField(auto_now_add=True)
    especialidad = models.CharField(max_length=100)
    motivo = models.TextField()
    observaciones = models.TextField(blank=True)

    class Meta:
        db_table = 'ReferenciaMedica'
        verbose_name = 'referencia médica'
        verbose_name_plural = 'referencias médicas'

    def __str__(self):
        return f'Referencia a {self.especialidad} · {self.consulta}'


class ControlPosterior(ModeloBase):
    class Estado(models.TextChoices):
        PENDIENTE = 'pendiente', 'Pendiente'
        ATENDIDO = 'atendido', 'Atendido'
        NO_ASISTIO = 'no_asistio', 'No asistió'
        APLAZADO = 'aplazado', 'Aplazado'

    consulta = models.ForeignKey(
        Consulta, on_delete=models.PROTECT, related_name='controles',
    )
    fecha_control = models.DateField()
    motivo = models.TextField()
    estado = models.CharField(
        max_length=15, choices=Estado.choices, default=Estado.PENDIENTE,
    )

    class Meta:
        db_table = 'ControlPosterior'
        verbose_name = 'control posterior'
        verbose_name_plural = 'controles posteriores'

    def __str__(self):
        return f'Control {self.fecha_control:%d/%m/%Y} · {self.consulta}'


class Aplicacion(ModeloBase):
    class Tipo(models.TextChoices):
        SUERO = 'suero', 'Suero'
        CURACION = 'curacion', 'Curación'
        NEBULIZACION = 'nebulizacion', 'Nebulización'
        OTRO = 'otro', 'Otro'

    consulta = models.ForeignKey(
        Consulta, on_delete=models.PROTECT, related_name='aplicaciones',
    )
    tipo = models.CharField(max_length=15, choices=Tipo.choices)
    dosis = models.CharField(max_length=100, blank=True)
    indicaciones = models.TextField(blank=True)

    ejecutada = models.BooleanField(default=False)
    ejecutada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='aplicaciones_ejecutadas',
    )
    fecha_ejecucion = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'Aplicacion'
        verbose_name = 'aplicación'
        verbose_name_plural = 'aplicaciones'

    def __str__(self):
        return f'{self.get_tipo_display()} · {self.consulta}'


class OrdenExamen(ModeloBase):
    """
    Independiente de Consulta (TEC-01): se relaciona con Persona
    directo, y opcionalmente con una Consulta -- puede existir sin
    ninguna (HU-EXP-20).
    """

    persona = models.ForeignKey(
        Persona, on_delete=models.PROTECT, related_name='ordenes_examen',
    )
    consulta = models.ForeignKey(
        Consulta, on_delete=models.PROTECT, null=True, blank=True,
        related_name='ordenes_examen',
    )
    doctor_nombre = models.CharField(max_length=150, blank=True)
    fecha = models.DateField(auto_now_add=True)
    indicaciones = models.TextField(blank=True)

    class Meta:
        db_table = 'OrdenExamen'
        verbose_name = 'orden de examen'
        verbose_name_plural = 'órdenes de examen'

    def __str__(self):
        return f'Orden de examen · {self.persona} · {self.fecha:%d/%m/%Y}'


class DetalleOrdenExamen(ModeloBase):
    orden = models.ForeignKey(
        OrdenExamen, on_delete=models.PROTECT, related_name='detalles',
    )
    tipo_examen = models.CharField(max_length=150)

    class Meta:
        db_table = 'DetalleOrdenExamen'
        verbose_name = 'detalle de orden de examen'
        verbose_name_plural = 'detalles de orden de examen'

    def __str__(self):
        return self.tipo_examen
