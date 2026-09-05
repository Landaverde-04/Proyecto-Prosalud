from datetime import date

from django.db import models

from core.models import Clinica, ModeloBase


def calcular_edad(fecha_nacimiento):
    """
    Edad en anios cumplidos a partir de una fecha de nacimiento.

    Vive aqui (no solo como metodo de Persona) porque HU-EXP-02 tambien
    la necesita en el formulario, antes de que exista un Persona guardado
    -- se usa para decidir si el paciente que se esta registrando es
    menor de edad, con la fecha que la enfermera acaba de escribir.
    """
    if not fecha_nacimiento:
        return None
    hoy = date.today()
    edad = hoy.year - fecha_nacimiento.year
    if (hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day):
        edad -= 1
    return edad


class Persona(ModeloBase):
    """
    Tabla unica de personas del sistema: un paciente es una Persona, y
    quien aparece como su contacto o responsable tambien es su propia
    Persona (TEC-01) -- no hay clases separadas Paciente/Responsable.

    Una Persona es "paciente de la clinica" cuando tiene un Expediente
    asociado (ver Expediente mas abajo), no por ningun campo aqui.
    """

    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    # Opcional y NUNCA llave: el mismo DUI puede repetirse entre un
    # paciente y su responsable. Unico solo cuando existe -- ver el
    # indice parcial en Meta.constraints.
    dui = models.CharField('DUI', max_length=10, blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    # Opcional: obligatoria para el paciente (HU-EXP-01/02 la exigen en
    # el formulario), pero un contacto de referencia solo necesita
    # nombre, parentesco y telefono -- su fecha de nacimiento no
    # siempre se conoce ni se pide.
    fecha_nacimiento = models.DateField(null=True, blank=True)
    sexo = models.CharField(max_length=10, blank=True)

    class Meta:
        db_table = 'Persona'
        verbose_name = 'persona'
        verbose_name_plural = 'personas'
        constraints = [
            models.UniqueConstraint(
                fields=['dui'],
                condition=~models.Q(dui=''),
                name='persona_dui_unico_si_existe',
            ),
        ]

    def __str__(self):
        return f'{self.nombres} {self.apellidos}'

    @property
    def edad(self):
        """None si no hay fecha de nacimiento (los contactos no siempre la tienen)."""
        return calcular_edad(self.fecha_nacimiento)


class Contacto(ModeloBase):
    """
    Relaciona una Persona (el paciente) con otra Persona (el contacto),
    guardando el tipo de relacion y el parentesco -- resuelve con una
    sola entidad si es responsable o contacto de referencia, en vez de
    dos clases (TEC-01).

    Al cumplir 18 anios y registrarse el DUI del paciente, el contacto
    de tipo RESPONSABLE se actualiza a REFERENCIA (mismo registro, no
    se crea uno nuevo) -- ver HU-EXP-03.
    """

    class Tipo(models.TextChoices):
        RESPONSABLE = 'responsable', 'Responsable'
        REFERENCIA = 'referencia', 'Contacto de referencia'

    class Parentesco(models.TextChoices):
        # Sin distinguir femenino/masculino: lo que importa es la
        # relacion, no el genero de quien la tiene.
        PADRE_MADRE = 'padre_madre', 'Padre/Madre'
        ESPOSO = 'esposo', 'Esposo(a)'
        HIJO = 'hijo', 'Hijo(a)'
        HERMANO = 'hermano', 'Hermano(a)'
        ABUELO = 'abuelo', 'Abuelo(a)'
        TIO = 'tio', 'Tío(a)'
        AMIGO = 'amigo', 'Amigo(a)'
        VECINO = 'vecino', 'Vecino(a)'
        OTRO = 'otro', 'Otro'

    paciente = models.ForeignKey(
        Persona, on_delete=models.PROTECT, related_name='contactos',
    )
    persona_contacto = models.ForeignKey(
        Persona, on_delete=models.PROTECT, related_name='es_contacto_de',
    )
    tipo = models.CharField(max_length=15, choices=Tipo.choices)
    # Lista cerrada, no texto libre: "hermana", "hrmana", "Hermana",
    # "hermanas" son la misma relacion pero cuatro valores distintos si
    # se escriben a mano. "Otro" + parentesco_otro cubre lo que no
    # encaja en la lista, sin perder el dato.
    parentesco = models.CharField(max_length=20, choices=Parentesco.choices)
    parentesco_otro = models.CharField(
        'detalle si es "otro"', max_length=100, blank=True,
    )

    class Meta:
        db_table = 'Contacto'
        verbose_name = 'contacto'
        verbose_name_plural = 'contactos'
        constraints = [
            # Una persona no puede ser contacto dos veces del mismo
            # paciente (TEC-01). El cambio de responsable a referencia
            # es una actualizacion de tipo sobre este mismo registro.
            models.UniqueConstraint(
                fields=['paciente', 'persona_contacto'],
                name='contacto_unico_por_paciente',
            ),
            # Nadie puede ser contacto de si mismo.
            models.CheckConstraint(
                condition=~models.Q(paciente=models.F('persona_contacto')),
                name='contacto_no_puede_ser_si_mismo',
            ),
        ]

    def __str__(self):
        return f'{self.persona_contacto} ({self.get_tipo_display()} de {self.paciente})'

    @property
    def parentesco_mostrado(self):
        """'Otro' no dice nada por si solo -- si hay detalle, se muestra ese."""
        if self.parentesco == self.Parentesco.OTRO and self.parentesco_otro:
            return self.parentesco_otro
        return self.get_parentesco_display()


class Expediente(ModeloBase):
    """
    Cuelga de Persona y pertenece a una Clinica. Una Persona puede tener
    un expediente por clinica, pero no mas de uno en la misma (TEC-01) --
    es lo que la convierte en "paciente" de esa clinica.
    """

    persona = models.ForeignKey(
        Persona, on_delete=models.PROTECT, related_name='expedientes',
    )
    clinica = models.ForeignKey(
        Clinica, on_delete=models.PROTECT, related_name='expedientes',
    )
    fecha_apertura = models.DateField(auto_now_add=True)

    class Meta:
        db_table = 'Expediente'
        verbose_name = 'expediente'
        verbose_name_plural = 'expedientes'
        constraints = [
            models.UniqueConstraint(
                fields=['persona', 'clinica'],
                name='expediente_unico_por_clinica',
            ),
        ]

    def __str__(self):
        return f'Expediente de {self.persona} en {self.clinica}'
