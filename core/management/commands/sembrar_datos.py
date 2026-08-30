from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Clinica
from pacientes.models import Contacto, Expediente, Persona

Usuario = get_user_model()


class Command(BaseCommand):
    """
    Comando unico de datos de prueba para todo el sistema (estilo
    "seeder" de Laravel), organizado por secciones -- una funcion por
    seccion, cada una documentando que tablas toca. Asi no hace falta
    un comando por app: agregar una seccion nueva es agregar una
    funcion aqui, no un archivo en cada app.

    Uso:
        python manage.py sembrar_datos              # siembra todo
        python manage.py sembrar_datos --limpiar     # borra lo sembrable y vuelve a sembrar

    --limpiar NO borra la seccion Seguridad: los roles ya se usan para
    iniciar sesion de verdad, no son datos de ejemplo desechables. Solo
    la seccion Pacientes se vacia y se vuelve a sembrar.
    """

    help = 'Siembra datos de prueba por secciones. Usa --limpiar para vaciar y volver a sembrar lo sembrable.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limpiar',
            action='store_true',
            help='Antes de sembrar, borra los datos de las secciones marcadas como sembrables (ver docstring).',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options['limpiar']:
            self.limpiar_pacientes()

        self.sembrar_seguridad()
        self.sembrar_pacientes()
        # Seccion Consultas: no existe todavia -- se agrega aqui cuando
        # haya un flujo real que probar (HU-EXP-17 en adelante). Mismo
        # patron: una funcion sembrar_consultas() con su propio
        # limpiar_consultas(), documentando sus tablas.

        self.stdout.write(self.style.SUCCESS('Listo.'))

    # ------------------------------------------------------------------
    # Seccion: Seguridad
    # Tablas: auth_group (Roles).
    # NUNCA se toca con --limpiar -- son los roles con los que la gente
    # inicia sesion de verdad, no datos de ejemplo.
    # ------------------------------------------------------------------
    def sembrar_seguridad(self):
        self.stdout.write('Seccion Seguridad (auth_group)')
        roles = ['Doctora Administradora', 'Doctor', 'Enfermera', 'Laboratorio', 'Regente']
        for nombre in roles:
            _, creado = Group.objects.get_or_create(name=nombre)
            etiqueta = 'creado' if creado else 'ya existia'
            self.stdout.write(f'  Rol {etiqueta}: {nombre}')

    # ------------------------------------------------------------------
    # Seccion: Pacientes
    # Tablas: core_clinica, pacientes_persona, pacientes_contacto,
    # pacientes_expediente.
    # Sembrable: --limpiar borra Persona/Contacto/Expediente (Clinica NO
    # se borra, es la clinica real del sistema, no un dato de ejemplo).
    # ------------------------------------------------------------------
    PACIENTES_DE_PRUEBA = [
        {
            'nombres': 'Maria Elena', 'apellidos': 'Hernandez Perez',
            'dui': '04521678-9', 'telefono': '7845-1122',
            'fecha_nacimiento': '1988-03-14', 'sexo': 'F',
            'contacto_tipo': Contacto.Tipo.REFERENCIA,
            'contacto_nombres': 'Carlos', 'contacto_apellidos': 'Hernandez Lopez',
            'contacto_telefono': '7845-1123', 'contacto_parentesco': 'Esposo',
        },
        {
            'nombres': 'Jose Roberto', 'apellidos': 'Munoz Castro',
            'dui': '06678123-4', 'telefono': '7233-4455',
            'fecha_nacimiento': '1975-11-30', 'sexo': 'M',
            'contacto_tipo': Contacto.Tipo.REFERENCIA,
            'contacto_nombres': 'Gloria', 'contacto_apellidos': 'Castro Ramirez',
            'contacto_telefono': '7233-4456', 'contacto_parentesco': 'Hermana',
        },
        {
            'nombres': 'Ana Beatriz', 'apellidos': 'Flores Alvarado',
            'dui': '05123456-7', 'telefono': '7011-2233',
            'fecha_nacimiento': '1990-01-22', 'sexo': 'F',
            'contacto_tipo': Contacto.Tipo.REFERENCIA,
            'contacto_nombres': 'Marta', 'contacto_apellidos': 'Alvarado Diaz',
            'contacto_telefono': '7011-2234', 'contacto_parentesco': 'Madre',
        },
        {
            'nombres': 'Santiago', 'apellidos': 'Martinez Lopez',
            'dui': '', 'telefono': '',
            'fecha_nacimiento': '2019-07-02', 'sexo': 'M',
            'contacto_tipo': Contacto.Tipo.RESPONSABLE,
            'contacto_nombres': 'Ana', 'contacto_apellidos': 'Lopez Garcia',
            'contacto_telefono': '7011-9988', 'contacto_parentesco': 'Madre',
        },
        {
            'nombres': 'Sofia Nicole', 'apellidos': 'Escobar Cruz',
            'dui': '', 'telefono': '',
            'fecha_nacimiento': '2015-09-05', 'sexo': 'F',
            'contacto_tipo': Contacto.Tipo.RESPONSABLE,
            'contacto_nombres': 'Patricia', 'contacto_apellidos': 'Cruz Fuentes',
            'contacto_telefono': '7456-6677', 'contacto_parentesco': 'Madre',
        },
    ]

    def limpiar_pacientes(self):
        self.stdout.write('Limpiando seccion Pacientes...')
        # El orden importa: Contacto y Expediente referencian a Persona
        # con PROTECT, asi que se borran primero.
        Contacto.objects.all().delete()
        Expediente.objects.all().delete()
        Persona.objects.all().delete()

    def sembrar_pacientes(self):
        self.stdout.write('Seccion Pacientes (core_clinica, pacientes_persona/contacto/expediente)')
        usuario_sistema = Usuario.objects.filter(is_superuser=True).order_by('id').first()

        clinica, creada = Clinica.objects.get_or_create(
            nombre='ProSalud',
            defaults={
                'direccion': 'San Salvador',
                'creado_por': usuario_sistema,
                'modificado_por': usuario_sistema,
            },
        )
        etiqueta = 'creada' if creada else 'ya existia'
        self.stdout.write(f'  Clinica {etiqueta}: {clinica.nombre}')

        for datos in self.PACIENTES_DE_PRUEBA:
            persona, creada = Persona.objects.get_or_create(
                nombres=datos['nombres'],
                apellidos=datos['apellidos'],
                fecha_nacimiento=datos['fecha_nacimiento'],
                defaults={
                    'dui': datos['dui'],
                    'telefono': datos['telefono'],
                    'sexo': datos['sexo'],
                    'creado_por': usuario_sistema,
                    'modificado_por': usuario_sistema,
                },
            )
            if not creada:
                self.stdout.write(f'  Ya existia: {persona}')
                continue

            persona_contacto, _ = Persona.objects.get_or_create(
                nombres=datos['contacto_nombres'],
                apellidos=datos['contacto_apellidos'],
                defaults={
                    'telefono': datos['contacto_telefono'],
                    'fecha_nacimiento': '1985-01-01',
                    'creado_por': usuario_sistema,
                    'modificado_por': usuario_sistema,
                },
            )
            Contacto.objects.create(
                paciente=persona,
                persona_contacto=persona_contacto,
                tipo=datos['contacto_tipo'],
                parentesco=datos['contacto_parentesco'],
                creado_por=usuario_sistema,
                modificado_por=usuario_sistema,
            )
            Expediente.objects.create(
                persona=persona,
                clinica=clinica,
                creado_por=usuario_sistema,
                modificado_por=usuario_sistema,
            )
            self.stdout.write(self.style.SUCCESS(f'  Creado: {persona} (expediente en {clinica})'))
