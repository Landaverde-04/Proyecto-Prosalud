import unicodedata

from django.db import migrations

ANTERIOR = 'Estética'
NUEVO = 'Centro de Medicina Estética'


def _normalizar(texto):
    sin_tildes = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode()
    return sin_tildes.strip().lower()


def renombrar(apps, schema_editor):
    """
    La clinica estetica pasa a llamarse como su marca real.

    Se renombra la fila que ya existe en vez de dejar que el comando de datos
    de prueba cree otra: buscar por nombre habria dejado dos clinicas, y los
    expedientes de la primera colgando de la que ya nadie usa.
    """
    Clinica = apps.get_model('core', 'Clinica')
    for clinica in Clinica.objects.all():
        if _normalizar(clinica.nombre) == _normalizar(ANTERIOR):
            clinica.nombre = NUEVO
            clinica.save(update_fields=['nombre'])


def deshacer(apps, schema_editor):
    Clinica = apps.get_model('core', 'Clinica')
    for clinica in Clinica.objects.all():
        if _normalizar(clinica.nombre) == _normalizar(NUEVO):
            clinica.nombre = ANTERIOR
            clinica.save(update_fields=['nombre'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_clinica_tipo_tema'),
    ]

    operations = [
        migrations.RunPython(renombrar, deshacer),
    ]
