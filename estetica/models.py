from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import ModeloBase
from pacientes.models import Expediente


class FichaEstetica(ModeloBase):
    """
    Ficha de ingreso de la paciente en la clinica estetica (HU-EST-01).

    Una por expediente de Estetica. Guarda solo lo que la ficha en papel
    pide y `Persona` no tiene: nombre, DUI, telefono, nacimiento y sexo
    siguen en `Persona`, compartidos con ProSalud. El motivo de consulta no
    va aqui: es de cada atencion (HU-EST-03).
    """

    class ComoConocio(models.TextChoices):
        ADWORDS = 'adwords', 'Adwords'
        AMIGO = 'amigo', 'Amigo'
        REFERIDO_PACIENTE = 'referido_paciente', 'Referido por paciente'
        REFERIDO_MEDICO = 'referido_medico', 'Referido por médico tratante'
        ESPONTANEO = 'espontaneo', 'Espontáneo'
        FACEBOOK = 'facebook', 'Facebook'
        FAMILIAR = 'familiar', 'Familiar'
        EMPLEADO = 'empleado', 'Empleado de la compañía'
        MAILING = 'mailing', 'Mailing'
        NO_ESPECIFICA = 'no_especifica', 'No especifica'
        PAGINA_WEB = 'pagina_web', 'Página web'

    class ResultadoDepilacion(models.TextChoices):
        BUENO = 'bueno', 'Bueno'
        MEDIO = 'medio', 'Medio'
        MALO = 'malo', 'Malo'

    expediente = models.OneToOneField(
        Expediente, on_delete=models.PROTECT, related_name='ficha_estetica',
    )
    estado_civil = models.CharField(max_length=30, blank=True)
    religion = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    ocupacion = models.CharField(max_length=100, blank=True)
    direccion = models.CharField(max_length=255, blank=True)
    # El "Medico:" de la ficha: su medico de cabecera o quien la refiere.
    medico = models.CharField(max_length=100, blank=True)
    como_conocio = models.CharField(max_length=20, choices=ComoConocio.choices, blank=True)
    # El "¿Quien?" de la ficha, para los referidos.
    referido_por = models.CharField(max_length=100, blank=True)

    # --- Antecedentes esteticos (HU-EST-02), en el orden de la ficha en papel ---
    # Cada Si/No admite tres estados: Si, No o sin responder (null). Asi un
    # "no" no se confunde con algo que no se pregunto.
    tratamiento_estetico = models.BooleanField(null=True, blank=True)
    tratamiento_estetico_cual = models.CharField(max_length=255, blank=True)
    cirugia = models.BooleanField(null=True, blank=True)
    cirugia_cuales = models.CharField(max_length=255, blank=True)
    cirugia_donde = models.CharField(max_length=150, blank=True)
    cirugia_doctor = models.CharField(max_length=100, blank=True)
    moldeamiento_corporal = models.BooleanField(null=True, blank=True)
    moldeamiento_corporal_cuales = models.CharField(max_length=255, blank=True)
    depilacion = models.BooleanField(null=True, blank=True)
    depilacion_laser = models.BooleanField(default=False)
    depilacion_ipl = models.BooleanField(default=False)
    depilacion_resultado = models.CharField(max_length=10, choices=ResultadoDepilacion.choices, blank=True)
    tratamientos_faciales = models.BooleanField(null=True, blank=True)
    tratamientos_faciales_cuales = models.CharField(max_length=255, blank=True)
    # Las casillas sueltas del papel: marcada o no, sin tercer estado.
    botox = models.BooleanField(default=False)
    rellenos = models.BooleanField(default=False)
    prp = models.BooleanField(default=False)
    laser = models.BooleanField(default=False)
    hilos = models.BooleanField(default=False)
    otros_procedimientos = models.CharField(max_length=255, blank=True)
    productos_en_casa = models.TextField(blank=True)

    # --- Antecedentes medicos (HU-EST-02), hoja 2 de la ficha en papel ---
    # Propios de la Estetica: no usan la tabla Antecedente de ProSalud. Las
    # clinicas son independientes (Samuel, 22/10/2026).
    enfermedad = models.BooleanField(null=True, blank=True)
    enfermedad_cuales = models.CharField(max_length=255, blank=True)
    cirugia_medica = models.BooleanField(null=True, blank=True)
    cirugia_medica_cual = models.CharField(max_length=255, blank=True)
    alergico = models.BooleanField(null=True, blank=True)
    alergico_a_que = models.CharField(max_length=255, blank=True)
    fracturas = models.BooleanField(null=True, blank=True)
    fracturas_donde = models.CharField(max_length=255, blank=True)
    embarazos = models.PositiveSmallIntegerField(null=True, blank=True)
    abortos = models.PositiveSmallIntegerField(null=True, blank=True)
    partos = models.PositiveSmallIntegerField(null=True, blank=True)
    cesareas = models.PositiveSmallIntegerField(null=True, blank=True)
    # Fecha de la ultima regla.
    fur = models.DateField(null=True, blank=True)
    ciclo_regular = models.BooleanField(null=True, blank=True)
    anticonceptivos = models.BooleanField(null=True, blank=True)
    anticonceptivos_cual = models.CharField(max_length=255, blank=True)
    menopausia_andropausia = models.BooleanField(null=True, blank=True)
    anestesia_previa = models.BooleanField(null=True, blank=True)
    enfermedades_familia = models.CharField(max_length=255, blank=True)
    problemas_orinar = models.BooleanField(default=False)
    problemas_defecar = models.BooleanField(default=False)
    problemas_dormir = models.BooleanField(default=False)
    hace_ejercicio = models.BooleanField(default=False)
    fuma = models.BooleanField(default=False)
    alcohol = models.BooleanField(default=False)
    dieta = models.CharField(max_length=255, blank=True)
    vitaminas_suplementos = models.CharField(max_length=255, blank=True)
    droga_recreacional = models.BooleanField(null=True, blank=True)
    droga_recreacional_cual = models.CharField(max_length=255, blank=True)
    pastillas_para_dormir = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = 'FichaEstetica'
        verbose_name = 'ficha estética'
        verbose_name_plural = 'fichas estéticas'

    def __str__(self):
        return f'Ficha estética de {self.expediente.persona}'


class AtencionEstetica(ModeloBase):
    """
    Cada visita de la paciente a la clinica estetica (HU-EST-03).

    Propia de la Estetica, independiente de la `Consulta` de ProSalud: no
    lleva SOAP, cola ni preconsulta. Sigue la hoja 2 y 3 de la ficha en
    papel: signos vitales, plan, RP y descripcion del tratamiento. Los
    procedimientos y sus sesiones van aparte porque son de la paciente y
    duran varias visitas.
    """

    expediente = models.ForeignKey(
        Expediente, on_delete=models.PROTECT, related_name='atenciones_esteticas',
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='atenciones_esteticas',
    )
    # Nombre congelado al crear, como en la consulta: si el perfil cambia
    # despues, la atencion sigue diciendo quien atendio ese dia.
    doctor_nombre = models.CharField(max_length=150, blank=True)
    inicio = models.DateTimeField(default=timezone.now)
    cierre = models.DateTimeField(null=True, blank=True)

    motivo = models.TextField(blank=True)
    presion_arterial = models.CharField(max_length=10, blank=True)
    frecuencia_cardiaca = models.PositiveSmallIntegerField(null=True, blank=True)
    temperatura = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    saturacion = models.PositiveSmallIntegerField(null=True, blank=True)
    peso = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    talla = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    plan = models.TextField(blank=True)
    # La receta, como el "RP:" de la ficha en papel.
    rp = models.TextField(blank=True)
    descripcion_tratamiento = models.TextField(blank=True)

    # Zonas a tratar: el dibujo de la ficha en papel (cara, frente y espalda),
    # con marcas que la doctora pone tocando la imagen.
    class Figura(models.TextChoices):
        MUJER = 'mujer', 'Mujer'
        HOMBRE = 'hombre', 'Hombre'

    figura = models.CharField(max_length=10, choices=Figura.choices, blank=True)
    # Lista de marcas: [{"x": 41.2, "y": 30.5, "nota": "..."}]. x e y son el
    # porcentaje del ancho y del alto de la imagen, asi la marca cae en el
    # mismo punto sin importar el tamano de la pantalla.
    marcas = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = 'AtencionEstetica'
        verbose_name = 'atención estética'
        verbose_name_plural = 'atenciones estéticas'
        ordering = ['-inicio']

    def __str__(self):
        return f'Atención de {self.expediente.persona} del {timezone.localtime(self.inicio):%d/%m/%Y}'

    @property
    def cerrada(self):
        return self.cierre is not None


class ProcedimientoEstetico(ModeloBase):
    """
    Un renglon de la tabla "Procedimiento | 1 ... 10" de la ficha en papel.
    Es de la paciente, no de una visita: sus sesiones se van marcando en
    atenciones distintas.
    """

    MAXIMO_SESIONES = 10

    expediente = models.ForeignKey(
        Expediente, on_delete=models.PROTECT, related_name='procedimientos_esteticos',
    )
    nombre = models.CharField(max_length=150)

    class Meta:
        db_table = 'ProcedimientoEstetico'
        verbose_name = 'procedimiento estético'
        verbose_name_plural = 'procedimientos estéticos'
        ordering = ['fecha_creacion']

    def __str__(self):
        return self.nombre


class SesionProcedimiento(ModeloBase):
    """Una casilla marcada de la tabla: la sesion N, hecha en una atencion."""

    procedimiento = models.ForeignKey(
        ProcedimientoEstetico, on_delete=models.PROTECT, related_name='sesiones',
    )
    numero = models.PositiveSmallIntegerField()
    atencion = models.ForeignKey(
        AtencionEstetica, on_delete=models.PROTECT, related_name='sesiones',
    )

    class Meta:
        db_table = 'SesionProcedimiento'
        verbose_name = 'sesión de procedimiento'
        verbose_name_plural = 'sesiones de procedimiento'
        ordering = ['numero']
        constraints = [
            # Dos veces la misma sesion de un procedimiento no tiene sentido;
            # tambien frena un doble clic que llegue dos veces al servidor.
            models.UniqueConstraint(fields=['procedimiento', 'numero'], condition=models.Q(activo=True),
                                    name='sesion_unica_por_numero'),
        ]

    def __str__(self):
        return f'{self.procedimiento} · sesión {self.numero}'

