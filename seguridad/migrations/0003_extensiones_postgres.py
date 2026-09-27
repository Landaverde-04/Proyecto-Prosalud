# Activa las extensiones de PostgreSQL que necesita la busqueda de
# pacientes: unaccent (para que "jose" encuentre "Jose") y pg_trgm (para
# que las busquedas parciales sigan siendo rapidas con miles de registros).

from django.contrib.postgres.operations import TrigramExtension, UnaccentExtension
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('seguridad', '0002_usuario_debe_cambiar_password'),
    ]

    operations = [
        UnaccentExtension(),
        TrigramExtension(),
    ]
