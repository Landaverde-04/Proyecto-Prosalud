from datetime import timedelta
import uuid

from django.conf import settings
from django.db import models

from core.models import ModeloBase
from pacientes.models import Expediente, Persona


class DocumentoDeConsulta:
    """
    Lo comun a los documentos que cuelgan de una consulta (constancia,
    referencia, y los que falten): quien los firma.

    No es un modelo, es una clase de apoyo -- no agrega columnas ni
    migraciones. Cada documento aporta sus propios campos.
    """

    @property
    def profesional_emisor(self):
        # `creado_por` es quien emitio. Los documentos anteriores a esa regla
        # no lo tienen, y ahi el medico de la consulta es el equivalente.
        return self.creado_por if self.creado_por_id else self.consulta.doctor

    @property
    def nombre_profesional(self):
        # El nombre SI se congela: puede cambiar (correccion, matrimonio) y un
        # documento ya emitido no debe cambiar de firmante por eso.
        if self.doctor_nombre:
            return self.doctor_nombre
        doctor = self.profesional_emisor
        return doctor.get_full_name() or doctor.username

    @property
    def jvpm_profesional(self):
        # El JVPM NO se congela: es un identificador permanente del medico, no
        # un dato que cambie. Copiarlo seria guardar la misma constante en cada
        # fila; si algun dia se corrige, debe corregirse en todos lados.
        return self.profesional_emisor.jvpm


class Consulta(ModeloBase):
    """
    Cuelga de Expediente, no de Persona directamente: asi obtiene su
    clinica del expediente al que pertenece, sin guardarla por separado
    (TEC-01) -- ver la propiedad `clinica` mas abajo.

    De los campos de la Cola de Consulta que trae el diagrama, por ahora
    solo esta `hora_llegada`; es_emergencia, motivo_prioridad y
    nota_retiro se agregan cuando se construyan sus historias.
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

    # La atencion empieza cuando la doctora pulsa "Iniciar consulta", NO
    # cuando se crea la fila (HU-EXP-17). Por eso no es `auto_now_add`: la
    # fila puede nacer antes, en la preconsulta de enfermeria (HU-EXP-09),
    # y ahi `inicio` vacio significa "en la cola, todavia sin atender".
    # Tampoco seria asignable con `auto_now_add`, y hace falta para
    # registrar a mano una atencion que ya ocurrio (corte de energia).
    inicio = models.DateTimeField(null=True, blank=True)
    cierre = models.DateTimeField(null=True, blank=True)

    # Momento en que el paciente entro a la cola. Vacio en las consultas
    # que la doctora crea directamente, que nunca pasaron por la cola.
    hora_llegada = models.DateTimeField(null=True, blank=True)

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
        fecha = f'{self.inicio:%d/%m/%Y}' if self.inicio else 'sin iniciar'
        return f'Consulta de {self.expediente.persona} · {fecha}'

    @property
    def clinica(self):
        return self.expediente.clinica

    # Los tres estados salen de las dos columnas que ya existen, sin
    # agregar un campo de estado que habria que mantener en sincronia.
    @property
    def en_cola(self):
        return self.inicio is None and self.cierre is None

    @property
    def en_atencion(self):
        """Consulta iniciada y sin finalizar: es el borrador que se preguarda."""
        return self.inicio is not None and self.cierre is None

    @property
    def cerrada(self):
        return self.cierre is not None


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


class Incapacidad(DocumentoDeConsulta, ModeloBase):
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
    fecha_inicio_incapacidad = models.DateField(null=True, blank=True)
    # Identifica una emisión, incluso si se repite el envío del formulario.
    solicitud_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    fecha_atencion = models.DateField(null=True, blank=True)

    @property
    def fecha_fin(self):
        if self.tipo == self.Tipo.INCAPACIDAD and self.fecha_inicio_incapacidad and self.dias:
            return self.fecha_inicio_incapacidad + timedelta(days=self.dias - 1)
        return None

    class Meta:
        db_table = 'Incapacidad'
        verbose_name = 'incapacidad o constancia'
        verbose_name_plural = 'incapacidades y constancias'

    def __str__(self):
        return f'{self.get_tipo_display()} {self.folio}'


class ReferenciaMedica(DocumentoDeConsulta, ModeloBase):
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


class Antecedente(ModeloBase):
    """
    Antecedente del PACIENTE, no de una consulta (HU-EXP-07).

    Cuelga del `Expediente`, asi que es informacion permanente que la
    doctora consulta y corrige, no algo que se vuelva a preguntar en cada
    visita: si un dia no se escribieran, esa consulta pareceria decir que
    el paciente no tiene alergias. Por eso `Consulta.antecedentes` y
    `Consulta.alergias` dejaron de pedirse en el formulario de atencion.

    Al colgar del expediente queda ademas acotado por clinica: lo
    registrado en ProSalud no aparece en Estetica.

    Vive en `consultas/` aunque su FK apunte a `pacientes` -- mismo
    criterio del reparto: Antecedente y Adjunto son de Samuel.
    """

    class Tipo(models.TextChoices):
        # Lista cerrada, no texto libre: con texto libre "alergia",
        # "alergias" y "Alergico" se guardan como tres cosas distintas
        # (le paso a Contacto.parentesco y hubo que migrarlo despues).
        # Las claves caben en los 15 caracteres que fija el diagrama.
        PATOLOGICO = 'PATOLOGICO', 'Patológico'
        ALERGICO = 'ALERGICO', 'Alérgico'
        QUIRURGICO = 'QUIRURGICO', 'Quirúrgico'
        GINECO = 'GINECO', 'Gineco-obstétrico'
        FAMILIAR = 'FAMILIAR', 'Familiar'
        HABITOS = 'HABITOS', 'Hábitos'
        OTRO = 'OTRO', 'Otro'

    expediente = models.ForeignKey(
        Expediente, on_delete=models.PROTECT, related_name='antecedentes',
    )
    tipo = models.CharField(max_length=15, choices=Tipo.choices)
    detalle = models.TextField()

    class Meta:
        db_table = 'Antecedente'
        verbose_name = 'antecedente'
        verbose_name_plural = 'antecedentes'
        ordering = ['tipo', '-fecha_creacion']

    def __str__(self):
        return f'{self.get_tipo_display()}: {self.detalle[:40]}'
