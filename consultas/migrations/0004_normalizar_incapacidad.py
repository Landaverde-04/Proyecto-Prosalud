from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('consultas', '0003_incapacidad_clinica_direccion_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='incapacidad', old_name='fecha_inicio',
            new_name='fecha_inicio_incapacidad',
        ),
        migrations.RemoveField(model_name='incapacidad', name='paciente_nombre'),
        migrations.RemoveField(model_name='incapacidad', name='doctor_jvpm'),
        migrations.RemoveField(model_name='incapacidad', name='clinica_nombre'),
        migrations.RemoveField(model_name='incapacidad', name='clinica_direccion'),
        migrations.RemoveField(model_name='incapacidad', name='clinica_telefono'),
    ]
