# Utilidades de Django para crear comandos de manage.py
from django.core.management.base import BaseCommand, CommandError
# Contenido en memoria que se puede guardar como si fuera un archivo
from django.core.files.base import ContentFile
# Almacenamiento por defecto: disco local o R2, según settings.py
from django.core.files.storage import default_storage


class Command(BaseCommand):
    # Texto que aparece en "python manage.py help probar_almacenamiento"
    help = 'Sube, lee y borra un archivo de prueba en el almacenamiento de adjuntos'

    def handle(self, *args, **opciones):
        # Muestra qué backend está activo (FileSystemStorage o S3Storage)
        self.stdout.write(f'Backend: {default_storage.__class__.__name__}')
        # Ruta de prueba, separada de la carpeta de expedientes reales
        ruta = 'pruebas-conexion/prueba.txt'
        try:
            # Sube un archivo pequeño; devuelve el nombre con que quedó guardado
            nombre = default_storage.save(ruta, ContentFile(b'ok ProSalud'))
            # Lo vuelve a abrir en modo binario de solo lectura
            with default_storage.open(nombre, 'rb') as archivo:
                # Lee todo su contenido para compararlo después
                contenido = archivo.read()
            # Borra el archivo de prueba para no dejar basura en el bucket
            default_storage.delete(nombre)
        except Exception as error:
            # Cualquier fallo (credenciales, bucket, red) se reporta claro
            raise CommandError(f'Falló la prueba: {error}')
        # Confirma que lo leído es exactamente lo que se subió
        if contenido != b'ok ProSalud':
            # Si no coincide, el almacenamiento está devolviendo otra cosa
            raise CommandError('El archivo leído no coincide con el subido')
        # Mensaje final en verde: las tres operaciones funcionaron
        self.stdout.write(self.style.SUCCESS('Almacenamiento OK: subir, leer y borrar funcionan'))
