from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction

from consultas.models import (
    Antecedente, Aplicacion, Consulta, ControlPosterior, DetalleOrdenExamen,
    DetalleReceta, Incapacidad, OrdenExamen, Receta, ReferenciaMedica, SignosVitales,
)
from core.models import Clinica, RegistroAuditoria
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
        python manage.py sembrar_datos                     # siembra todo
        python manage.py sembrar_datos --limpiar           # borra consultas y pacientes, y vuelve a sembrar
        python manage.py sembrar_datos --limpiar-usuarios  # ademas borra las cuentas de prueba

    --limpiar NO borra la seccion Seguridad: los roles y las cuentas ya
    se usan para iniciar sesion de verdad. Para eso esta el flag aparte
    --limpiar-usuarios, que ademas implica --limpiar (las consultas
    referencian al doctor con PROTECT, hay que borrarlas primero).
    Los superusuarios nunca se borran: son la cuenta de rescate.
    """

    help = 'Siembra datos de prueba por secciones. Usa --limpiar para vaciar y volver a sembrar lo sembrable.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limpiar',
            action='store_true',
            help='Antes de sembrar, borra los datos de las secciones marcadas como sembrables (ver docstring).',
        )
        parser.add_argument(
            '--limpiar-usuarios',
            action='store_true',
            help='Ademas de --limpiar, borra las cuentas de prueba (nunca los superusuarios).',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        limpiar_usuarios = options['limpiar_usuarios']
        if options['limpiar'] or limpiar_usuarios:
            self.limpiar_consultas()
            self.limpiar_pacientes()
        if limpiar_usuarios:
            self.limpiar_usuarios()

        self.sembrar_clinicas()
        self.sembrar_seguridad()
        self.sembrar_pacientes()

        self.stdout.write(self.style.SUCCESS('Listo.'))

    # ------------------------------------------------------------------
    # Seccion: Consultas
    # Tablas: Consulta, SignosVitales, Antecedente y los documentos que
    # cuelgan de una consulta (Receta, Incapacidad, ReferenciaMedica,
    # ControlPosterior, Aplicacion, OrdenExamen y sus detalles).
    # No se siembra: las consultas nacen usando el sistema. Solo se
    # limpia, porque Consulta y Antecedente referencian al Expediente
    # con PROTECT y sin borrarlas no se puede vaciar Pacientes.
    # ------------------------------------------------------------------
    def limpiar_consultas(self):
        self.stdout.write('Limpiando seccion Consultas...')
        # De las hojas hacia la raiz: todo referencia con PROTECT, asi
        # que el orden no es opcional.
        for modelo in (
            DetalleReceta, DetalleOrdenExamen,
            Receta, Incapacidad, ReferenciaMedica, ControlPosterior, Aplicacion, OrdenExamen,
            SignosVitales, Consulta, Antecedente,
        ):
            borrados, _ = modelo.objects.all().delete()
            if borrados:
                self.stdout.write(f'  {modelo.__name__}: {borrados} borrados')

    # ------------------------------------------------------------------
    # Seccion: Usuarios de prueba (solo limpieza, la siembra la hace
    # sembrar_seguridad). Aparte de --limpiar a proposito: borrar cuentas
    # no debe ser un efecto secundario de refrescar los datos de ejemplo.
    # ------------------------------------------------------------------
    def limpiar_usuarios(self):
        self.stdout.write('Limpiando usuarios de prueba...')
        borrables = Usuario.objects.filter(is_superuser=False)
        # La bitacora referencia al usuario con PROTECT y no se borra
        # sola: se quitan sus entradas antes que la cuenta.
        RegistroAuditoria.objects.filter(usuario__in=borrables).delete()
        for usuario in borrables:
            nombre = usuario.username
            usuario.delete()
            self.stdout.write(f'  Usuario borrado: {nombre}')
        conservados = list(
            Usuario.objects.filter(is_superuser=True).values_list('username', flat=True)
        )
        if conservados:
            self.stdout.write(f'  Superusuarios conservados: {", ".join(conservados)}')

    # ------------------------------------------------------------------
    # Seccion: Clinicas
    # Tablas: core_clinica.
    # Va antes de Seguridad y Pacientes porque las dos la necesitan
    # (Usuario.clinicas y Expediente.clinica). NUNCA se toca con
    # --limpiar -- son las clinicas reales del sistema, no datos de
    # ejemplo.
    # ------------------------------------------------------------------
    def sembrar_clinicas(self):
        self.stdout.write('Seccion Clinicas (core_clinica)')
        for nombre in ['ProSalud', 'Estética']:
            _, creada = Clinica.objects.get_or_create(nombre=nombre)
            etiqueta = 'creada' if creada else 'ya existia'
            self.stdout.write(f'  Clinica {etiqueta}: {nombre}')

    # ------------------------------------------------------------------
    # Seccion: Seguridad
    # Tablas: auth_group (Roles), Usuario (solo los de prueba), UsuarioClinica.
    # NUNCA se toca con --limpiar -- son los roles y cuentas con los que
    # la gente inicia sesion de verdad, no datos de ejemplo.
    # ------------------------------------------------------------------

    # Un usuario por rol, para poder probar cada pantalla (ej. HU-EXP-05,
    # que exige el permiso view_expediente + pertenecer a la clinica) sin
    # tener que crear una cuenta a mano despues de clonar el proyecto.
    # La doctora administradora pertenece a las dos clinicas (regla de
    # negocio: TEC-01); el resto del personal solo a ProSalud.
    USUARIOS_DE_PRUEBA = [
        {
            'username': 'doctora', 'first_name': 'Elsa Cecilia', 'last_name': 'Miranda Velasquez',
            'rol': 'Doctora Administradora', 'clinicas': ['ProSalud', 'Estética'],
        },
        {
            'username': 'doctor1', 'first_name': 'Carlos', 'last_name': 'Rivas Aguilar',
            'rol': 'Doctor', 'clinicas': ['ProSalud'],
        },
        {
            'username': 'doctor2', 'first_name': 'Ana Lucia', 'last_name': 'Portillo Mejia',
            'rol': 'Doctor', 'clinicas': ['ProSalud'],
        },
        {
            'username': 'doctor3', 'first_name': 'Mario', 'last_name': 'Guzman Serrano',
            'rol': 'Doctor', 'clinicas': ['ProSalud'],
        },
        {
            'username': 'enfermera1', 'first_name': 'Marta', 'last_name': 'Gonzalez Peña',
            'rol': 'Enfermera', 'clinicas': ['ProSalud'],
        },
        {
            'username': 'enfermera2', 'first_name': 'Rocio', 'last_name': 'Alfaro Menjivar',
            'rol': 'Enfermera', 'clinicas': ['ProSalud'],
        },
        {
            'username': 'laboratorio1', 'first_name': 'Jorge', 'last_name': 'Aguilar Castro',
            'rol': 'Laboratorio', 'clinicas': ['ProSalud'],
        },
        {
            'username': 'regente1', 'first_name': 'Silvia', 'last_name': 'Ramos Flores',
            'rol': 'Regente', 'clinicas': ['ProSalud'],
        },
    ]
    # Contraseña de las cuentas de arriba -- documentada tambien en
    # COMANDOS_DATOS_PRUEBA.txt. Son cuentas de prueba locales, no de
    # produccion, por eso vive en el codigo sin problema.
    PASSWORD_USUARIOS_PRUEBA = 'admin'

    def sembrar_seguridad(self):
        self.stdout.write('Seccion Seguridad (auth_group)')
        roles = ['Doctora Administradora', 'Doctor', 'Enfermera', 'Laboratorio', 'Regente']
        for nombre in roles:
            _, creado = Group.objects.get_or_create(name=nombre)
            etiqueta = 'creado' if creado else 'ya existia'
            self.stdout.write(f'  Rol {etiqueta}: {nombre}')

        for datos in self.USUARIOS_DE_PRUEBA:
            usuario, creado = Usuario.objects.get_or_create(
                username=datos['username'],
                defaults={'first_name': datos['first_name'], 'last_name': datos['last_name']},
            )
            # La contraseña se reescribe siempre, no solo al crear: si
            # alguien la cambio probando, volver a correr el comando la
            # deja otra vez en la documentada, igual que el rol y la
            # clinica de abajo.
            usuario.set_password(self.PASSWORD_USUARIOS_PRUEBA)
            usuario.save()
            # set() en vez de add(): si se vuelve a correr el comando
            # despues de que alguien le cambio el rol o la clinica a mano,
            # esto lo regresa a su estado de prueba esperado -- coherente
            # con que estas cuentas son "protegidas", no desechables, pero
            # su configuracion SI debe reflejar siempre este comando.
            usuario.groups.set([Group.objects.get(name=datos['rol'])])
            usuario.clinicas.set(Clinica.objects.filter(nombre__in=datos['clinicas']))
            etiqueta = 'creado' if creado else 'ya existia'
            self.stdout.write(f'  Usuario {etiqueta}: {datos["username"]} ({datos["rol"]})')

    # ------------------------------------------------------------------
    # Seccion: Pacientes
    # Tablas: pacientes_persona, pacientes_contacto, pacientes_expediente
    # (la Clinica que usan ya la sembro sembrar_clinicas()).
    # Sembrable: --limpiar borra Persona/Contacto/Expediente.
    # 12 pacientes (mezcla de adultos y menores, con y sin DUI) -- lo
    # suficiente para ver la paginacion real de HU-EXP-04 (10 por
    # pagina), no solo un puñado que siempre cabe en una sola pagina.
    # ------------------------------------------------------------------
    PACIENTES_DE_PRUEBA = [
        {
            'nombres': 'Maria Elena', 'apellidos': 'Hernandez Perez',
            'dui': '04521678-9', 'telefono': '7845-1122',
            'fecha_nacimiento': '1988-03-14', 'sexo': 'F',
            'contacto_tipo': Contacto.Tipo.REFERENCIA,
            'contacto_nombres': 'Carlos', 'contacto_apellidos': 'Hernandez Lopez',
            'contacto_telefono': '7845-1123', 'contacto_parentesco': Contacto.Parentesco.ESPOSO,
        },
        {
            'nombres': 'Jose Roberto', 'apellidos': 'Munoz Castro',
            'dui': '06678123-4', 'telefono': '7233-4455',
            'fecha_nacimiento': '1975-11-30', 'sexo': 'M',
            'contacto_tipo': Contacto.Tipo.REFERENCIA,
            'contacto_nombres': 'Gloria', 'contacto_apellidos': 'Castro Ramirez',
            'contacto_telefono': '7233-4456', 'contacto_parentesco': Contacto.Parentesco.HERMANO,
        },
        {
            'nombres': 'Ana Beatriz', 'apellidos': 'Flores Alvarado',
            'dui': '05123456-7', 'telefono': '7011-2233',
            'fecha_nacimiento': '1990-01-22', 'sexo': 'F',
            'contacto_tipo': Contacto.Tipo.REFERENCIA,
            'contacto_nombres': 'Marta', 'contacto_apellidos': 'Alvarado Diaz',
            'contacto_telefono': '7011-2234', 'contacto_parentesco': Contacto.Parentesco.PADRE_MADRE,
        },
        {
            'nombres': 'Santiago', 'apellidos': 'Martinez Lopez',
            'dui': '', 'telefono': '',
            'fecha_nacimiento': '2019-07-02', 'sexo': 'M',
            'contacto_tipo': Contacto.Tipo.RESPONSABLE,
            'contacto_nombres': 'Ana', 'contacto_apellidos': 'Lopez Garcia',
            'contacto_telefono': '7011-9988', 'contacto_parentesco': Contacto.Parentesco.PADRE_MADRE,
        },
        {
            'nombres': 'Sofia Nicole', 'apellidos': 'Escobar Cruz',
            'dui': '', 'telefono': '',
            'fecha_nacimiento': '2015-09-05', 'sexo': 'F',
            'contacto_tipo': Contacto.Tipo.RESPONSABLE,
            'contacto_nombres': 'Patricia', 'contacto_apellidos': 'Cruz Fuentes',
            'contacto_telefono': '7456-6677', 'contacto_parentesco': Contacto.Parentesco.PADRE_MADRE,
        },
        {
            'nombres': 'Carlos Alberto', 'apellidos': 'Ramirez Cortez',
            'dui': '02233445-6', 'telefono': '7899-1122',
            'fecha_nacimiento': '1978-05-20', 'sexo': 'M',
            'contacto_tipo': Contacto.Tipo.REFERENCIA,
            'contacto_nombres': 'Blanca', 'contacto_apellidos': 'Ramirez Cortez',
            'contacto_telefono': '7899-1123', 'contacto_parentesco': Contacto.Parentesco.HERMANO,
        },
        {
            'nombres': 'Blanca Estela', 'apellidos': 'Diaz Molina',
            'dui': '', 'telefono': '7344-5566',
            'fecha_nacimiento': '1995-11-08', 'sexo': 'F',
            'contacto_tipo': Contacto.Tipo.REFERENCIA,
            'contacto_nombres': 'Marvin', 'contacto_apellidos': 'Diaz Molina',
            'contacto_telefono': '7344-5567', 'contacto_parentesco': Contacto.Parentesco.ESPOSO,
        },
        {
            'nombres': 'Fernando Jose', 'apellidos': 'Aguilar Reyes',
            'dui': '03344556-7', 'telefono': '',
            'fecha_nacimiento': '1960-02-14', 'sexo': 'M',
            'contacto_tipo': Contacto.Tipo.REFERENCIA,
            'contacto_nombres': 'Rosa', 'contacto_apellidos': 'Aguilar Reyes',
            'contacto_telefono': '7566-7788', 'contacto_parentesco': Contacto.Parentesco.HIJO,
        },
        {
            'nombres': 'Camila Renata', 'apellidos': 'Portillo Vasquez',
            'dui': '', 'telefono': '',
            'fecha_nacimiento': '2017-08-30', 'sexo': 'F',
            'contacto_tipo': Contacto.Tipo.RESPONSABLE,
            'contacto_nombres': 'Elena', 'contacto_apellidos': 'Vasquez Rivas',
            'contacto_telefono': '7677-8899', 'contacto_parentesco': Contacto.Parentesco.PADRE_MADRE,
        },
        {
            'nombres': 'Diego Alejandro', 'apellidos': 'Chavez Fuentes',
            'dui': '', 'telefono': '',
            'fecha_nacimiento': '2012-12-01', 'sexo': 'M',
            'contacto_tipo': Contacto.Tipo.RESPONSABLE,
            'contacto_nombres': 'Miguel', 'contacto_apellidos': 'Chavez Ortiz',
            'contacto_telefono': '7788-9900', 'contacto_parentesco': Contacto.Parentesco.PADRE_MADRE,
        },
        {
            'nombres': 'Gloria Patricia', 'apellidos': 'Mejia Sorto',
            'dui': '04455667-8', 'telefono': '7900-1234',
            'fecha_nacimiento': '1985-07-19', 'sexo': 'F',
            'contacto_tipo': Contacto.Tipo.REFERENCIA,
            'contacto_nombres': 'Walter', 'contacto_apellidos': 'Mejia Sorto',
            'contacto_telefono': '7900-1235', 'contacto_parentesco': Contacto.Parentesco.HERMANO,
        },
        {
            'nombres': 'Oscar Ivan', 'apellidos': 'Recinos Palma',
            'dui': '', 'telefono': '7011-3344',
            'fecha_nacimiento': '2001-03-25', 'sexo': 'M',
            'contacto_tipo': Contacto.Tipo.REFERENCIA,
            'contacto_nombres': 'Sandra', 'contacto_apellidos': 'Recinos Palma',
            'contacto_telefono': '7011-3345', 'contacto_parentesco': Contacto.Parentesco.TIO,
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
        self.stdout.write('Seccion Pacientes (pacientes_persona/contacto/expediente)')
        usuario_sistema = Usuario.objects.filter(is_superuser=True).order_by('id').first()

        # La clinica ya la crea sembrar_clinicas() (corre antes, en
        # handle()) -- aqui solo se usa.
        clinica = Clinica.objects.get(nombre='ProSalud')

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
