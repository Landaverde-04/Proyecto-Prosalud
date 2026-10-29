"""
Estado civil y religion pasan a opciones para marcar, y "como conocio la
clinica" pasa de un valor a una lista de casillas (29/10/2026).

Lo ya guardado se convierte: el valor de "como conocio" queda como unico
elemento de la lista, y un estado civil o religion escritos a mano se
traducen a la opcion que corresponda. Si una religion escrita no coincide con
ninguna opcion, queda como "otra"; un estado civil que no coincide queda vacio.
"""
import unicodedata

from django.db import migrations, models


def _normal(texto):
    sin_tildes = unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode()
    return sin_tildes.strip().lower()


def _estado_civil(texto):
    texto = _normal(texto)
    for inicio, clave in (('solter', 'soltera'), ('casad', 'casada'), ('acompa', 'acompanada'),
                          ('union', 'acompanada'), ('divorc', 'divorciada'), ('viud', 'viuda')):
        if texto.startswith(inicio):
            return clave
    return ''


def _religion(texto):
    texto = _normal(texto)
    if not texto:
        return ''
    for inicio, clave in (('catol', 'catolica'), ('evang', 'evangelica'), ('cristian', 'evangelica'),
                          ('ningun', 'ninguna'), ('ateo', 'ninguna')):
        if texto.startswith(inicio):
            return clave
    return 'otra'


def convertir(apps, schema_editor):
    FichaEstetica = apps.get_model('estetica', 'FichaEstetica')
    for ficha in FichaEstetica.objects.all():
        ficha.como_conocio_lista = [ficha.como_conocio] if ficha.como_conocio else []
        ficha.estado_civil = _estado_civil(ficha.estado_civil)
        ficha.religion = _religion(ficha.religion)
        ficha.save(update_fields=['como_conocio_lista', 'estado_civil', 'religion'])


def revertir(apps, schema_editor):
    FichaEstetica = apps.get_model('estetica', 'FichaEstetica')
    for ficha in FichaEstetica.objects.all():
        ficha.como_conocio = (ficha.como_conocio_lista or [''])[0]
        ficha.save(update_fields=['como_conocio'])


class Migration(migrations.Migration):

    dependencies = [
        ('estetica', '0005_zonas_a_tratar'),
    ]

    operations = [
        migrations.AddField(
            model_name='fichaestetica',
            name='como_conocio_lista',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(convertir, revertir),
        migrations.RemoveField(
            model_name='fichaestetica',
            name='como_conocio',
        ),
        migrations.RenameField(
            model_name='fichaestetica',
            old_name='como_conocio_lista',
            new_name='como_conocio',
        ),
        migrations.AlterField(
            model_name='fichaestetica',
            name='estado_civil',
            field=models.CharField(blank=True, choices=[
                ('soltera', 'Soltera/o'), ('casada', 'Casada/o'), ('acompanada', 'Acompañada/o'),
                ('divorciada', 'Divorciada/o'), ('viuda', 'Viuda/o')], max_length=30),
        ),
        migrations.AlterField(
            model_name='fichaestetica',
            name='religion',
            field=models.CharField(blank=True, choices=[
                ('catolica', 'Católica'), ('evangelica', 'Evangélica'), ('otra', 'Otra'),
                ('ninguna', 'Ninguna')], max_length=50),
        ),
    ]
