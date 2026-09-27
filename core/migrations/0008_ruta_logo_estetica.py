from django.db import migrations

ANTERIOR = 'core/img/logo_estetica.svg'
NUEVO = 'core/img/logo_estetica.png'


def corregir_ruta(apps, schema_editor):
    """
    El logo de la clinica estetica paso de un SVG dibujado a mano al logo
    real, en PNG, y el archivo viejo ya no existe.

    `Clinica.logo` guarda la ruta del archivo estatico, asi que una base que
    quedo con la ruta vieja pide un archivo que no esta. Con DEBUG=False el
    almacenamiento de estaticos no devuelve un hueco: lanza un error y la
    pagina no carga. Editar la migracion que escribio la ruta no sirve --
    esa ya corrio en esas bases; por eso la correccion va aparte.
    """
    Clinica = apps.get_model('core', 'Clinica')
    Clinica.objects.filter(logo=ANTERIOR).update(logo=NUEVO)


def deshacer(apps, schema_editor):
    Clinica = apps.get_model('core', 'Clinica')
    Clinica.objects.filter(logo=NUEVO).update(logo=ANTERIOR)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_clinica_nombre_corto'),
    ]

    operations = [
        migrations.RunPython(corregir_ruta, deshacer),
    ]
