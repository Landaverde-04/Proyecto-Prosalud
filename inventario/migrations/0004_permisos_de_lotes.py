"""
Da a la Doctora Administradora los permisos de lotes y movimientos (INV-02),
igual que 0002 hizo con los productos: los roles que ya existen no se
vuelven a armar solos.
"""
from django.contrib.auth.management import create_permissions
from django.db import migrations

PERMISOS = {
    'Doctora Administradora': ['view_lote', 'add_lote', 'change_lote', 'view_movimientoinventario'],
}


def dar_permisos(apps, schema_editor):
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
    for nombre, codigos in PERMISOS.items():
        rol = Group.objects.filter(name=nombre).first()
        if rol:
            rol.permissions.remove(*Permission.objects.filter(
                content_type__app_label='inventario', codename__in=codigos))


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0003_lotes_y_movimientos'),
    ]

    operations = [
        migrations.RunPython(dar_permisos, quitar_permisos),
    ]
