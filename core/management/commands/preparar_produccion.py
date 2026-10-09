"""
Deja una base recien migrada lista para trabajar: clinicas y roles.

No es `sembrar_datos`. Ese crea pacientes de ejemplo y cuentas con
contrasena conocida, y NUNCA debe correr en produccion. Este solo crea lo
que el sistema necesita para funcionar y no crea ningun usuario del
personal: esos se dan de alta desde la pantalla de Usuarios.

Corre en cada arranque del servicio, asi que es deliberadamente
conservador: crea lo que falta y no toca lo que ya existe.
"""
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Clinica
from seguridad.forms import permisos_asignables

# Las dos clinicas reales. La direccion y el telefono se dejan vacios a
# proposito: se cargan cuando la clinica los confirme.
CLINICAS = [
    {'nombre': 'ProSalud', 'nombre_corto': '',
     'tipo': Clinica.Tipo.MEDICA, 'tema': Clinica.Tema.VERDE_SALUD,
     'logo': 'core/img/logo_prosalud.svg'},
    {'nombre': 'Centro de Medicina Estética', 'nombre_corto': 'Estética',
     'tipo': Clinica.Tipo.ESTETICA, 'tema': Clinica.Tema.ESTETICA,
     'logo': 'core/img/logo_estetica.png'},
]

# Permisos de cada puesto, tal como estan en el Word de Roles y Permisos.
# 'TODOS' es la Doctora Administradora, que lleva el catalogo completo.
ROLES = {
    'Doctora Administradora': 'TODOS',
    'Doctor': [
        'pacientes.view_persona', 'pacientes.add_persona', 'pacientes.change_persona',
        'pacientes.view_expediente',
        'consultas.view_consulta', 'consultas.add_consulta', 'consultas.change_consulta',
        'consultas.view_antecedente', 'consultas.add_antecedente', 'consultas.change_antecedente',
        'consultas.view_incapacidad', 'consultas.add_incapacidad',
        'consultas.view_referenciamedica', 'consultas.add_referenciamedica',
        'consultas.view_controlposterior', 'consultas.add_controlposterior',
        'consultas.change_controlposterior',
        'consultas.view_aplicacion', 'consultas.add_aplicacion', 'consultas.change_aplicacion',
        'consultas.view_receta', 'consultas.add_receta', 'consultas.change_receta',
        'consultas.view_ordenexamen', 'consultas.add_ordenexamen',
        # Adjuntos: ver y agregar. Retirar es de la administradora.
        'consultas.view_adjunto', 'consultas.add_adjunto',
    ],
    'Enfermera': [
        'pacientes.view_persona', 'pacientes.add_persona', 'pacientes.change_persona',
        'consultas.view_consulta', 'consultas.add_consulta',
        'consultas.add_signosvitales', 'consultas.change_signosvitales',
    ],
    'Secretaria': [
        'pacientes.view_persona', 'pacientes.add_persona',
    ],
    # Sus modulos no existen todavia; el rol si, para poder asignarlo.
    'Laboratorio': [],
    'Regente': [],
}


class Command(BaseCommand):
    help = 'Crea las clinicas y los roles que el sistema necesita para operar'

    @transaction.atomic
    def handle(self, *args, **opciones):
        self.stdout.write('Clinicas')
        for datos in CLINICAS:
            _, creada = Clinica.objects.get_or_create(
                nombre=datos['nombre'], defaults=datos)
            self.stdout.write(f'  {datos["nombre"]}: {"creada" if creada else "ya existia"}')

        self.stdout.write('Roles')
        for nombre, codigos in ROLES.items():
            rol, creado = Group.objects.get_or_create(name=nombre)
            if not creado:
                # Un rol que ya existe se deja intacto: puede haber ajustes
                # hechos a mano desde la pantalla de Roles, y este comando
                # corre en cada arranque -- no debe deshacerlos.
                self.stdout.write(f'  {nombre}: ya existia, sin tocar')
                continue
            rol.permissions.set(self._permisos(codigos))
            self.stdout.write(f'  {nombre}: creado con {rol.permissions.count()} permisos')

        self.stdout.write(self.style.SUCCESS('Base lista para operar'))

    def _permisos(self, codigos):
        if codigos == 'TODOS':
            return permisos_asignables()
        pares = [codigo.split('.') for codigo in codigos]
        encontrados = Permission.objects.none()
        for app_label, codename in pares:
            encontrados = encontrados | Permission.objects.filter(
                content_type__app_label=app_label, codename=codename)
        faltantes = len(pares) - encontrados.count()
        if faltantes:
            # Un permiso que no existe suele significar una migracion sin
            # aplicar; mejor decirlo que dejar el rol a medias en silencio.
            self.stdout.write(self.style.WARNING(
                f'  ⚠ {faltantes} permiso(s) de la lista no existen en esta base'))
        return encontrados
