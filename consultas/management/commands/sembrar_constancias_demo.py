"""Crea dos ejemplos locales de HU-EXP-22, sin duplicarlos al repetir."""
import uuid
from datetime import datetime, time, timedelta
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from pacientes.models import Expediente
from seguridad.models import Usuario
from consultas.models import Consulta, Incapacidad
from consultas.views import datos_documento


class Command(BaseCommand):
    help = 'Crea dos constancias ficticias asociadas a consultas de demostración (solo DEBUG).'

    def add_arguments(self, parser):
        parser.add_argument('--expediente', type=int, required=True)
        parser.add_argument('--doctor', required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('Este comando solo está disponible en desarrollo con DEBUG=True.')
        expediente = Expediente.objects.select_related('persona', 'clinica').get(pk=options['expediente'])
        doctor = Usuario.objects.get(username=options['doctor'])
        if not doctor.clinicas.filter(pk=expediente.clinica_id).exists():
            raise CommandError('El usuario no pertenece a la clínica del expediente.')
        for indice, diferencia in enumerate((2, 0), 1):
            solicitud = uuid.uuid5(uuid.NAMESPACE_URL, f'prosalud/hu22/demo/{expediente.pk}/{indice}')
            existente = Incapacidad.objects.filter(solicitud_id=solicitud).first()
            if existente:
                self.stdout.write(f'Ya existe {existente.folio}; no se duplicó.')
                continue
            fecha = timezone.localdate() - timedelta(days=diferencia)
            consulta = Consulta.objects.create(expediente=expediente, doctor=doctor,
                doctor_nombre=doctor.get_full_name() or doctor.username,
                motivo=f'DEMOSTRACIÓN HU-EXP-22: atención ficticia {indice} para probar documentos.',
                creado_por=doctor, modificado_por=doctor)
            inicio = timezone.make_aware(datetime.combine(fecha, time(9, 0)))
            Consulta.objects.filter(pk=consulta.pk).update(inicio=inicio, cierre=inicio+timedelta(minutes=20))
            consulta.refresh_from_db()
            campos = datos_documento(consulta, {'tipo':'incapacidad', 'dias':2 if indice == 1 else 5, 'fecha_inicio':fecha, 'motivo':
                f'DOCUMENTO DE DEMOSTRACIÓN SIN VALIDEZ CLÍNICA. Ejemplo {indice} de atención ficticia para comprobar el expediente y la impresión.'})
            documento = Incapacidad.objects.create(**campos, solicitud_id=solicitud,
                                                     creado_por=doctor, modificado_por=doctor)
            # Solo los datos de demostración tienen fechas históricas simuladas.
            folio = f'DEMO-{documento.pk:08d}'
            Incapacidad.objects.filter(pk=documento.pk).update(fecha=fecha, folio=folio)
            self.stdout.write(f'{expediente.persona}: {folio}, {fecha:%d/%m/%Y}.')
