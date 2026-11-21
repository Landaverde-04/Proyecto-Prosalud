"""
Da los permisos del inventario a los roles que ya existen en la base.

preparar_produccion solo arma los roles la primera vez y despues no los
toca (pueden tener ajustes hechos a mano), asi que sin esto nadie veria el
inventario hasta asignarlo desde la pantalla de Roles. En una base nueva no
hay roles todavia y esto no hace nada: ahi los arma preparar_produccion.
"""
from django.contrib.auth.management import create_permissions
from django.db import migrations

PERMISOS = {
    'Doctora Administradora': ['view_producto', 'add_producto', 'change_producto'],
    'Doctor': ['view_producto'],
    'Enfermera': ['view_producto'],
}


def dar_permisos(apps, schema_editor):
    # Django crea los permisos al terminar todas las migraciones; aqui se
    # necesitan antes, asi que se crean ya (si existen, no se repiten).
    configuracion = apps.get_app_config('inventario')
    configuracion.models_module = True
    create_permissions(configuracion, apps=apps, verbosity=0)
    configuracion.models_module = None

    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    for nombre, codigos in PERMISOS.items():
        rol = Group.objects.filter(name=nombre).first()
        if rol:
            rol.permissions.add(*Permission.objects.filter(
                content_type__app_label='inventario', codename__in=codigos))


def quitar_permisos(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    permisos = Permission.objects.filter(content_type__app_label='inventario')
    for rol in Group.objects.filter(name__in=PERMISOS):
        rol.permissions.remove(*permisos)


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0001_producto'),
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.RunPython(dar_permisos, quitar_permisos),
    ]
