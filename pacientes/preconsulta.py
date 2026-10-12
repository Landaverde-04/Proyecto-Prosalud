"""Correcciones de signos compartidas por enfermeria y la consulta medica."""
from decimal import Decimal

from core.auditoria import registrar
from core.models import RegistroAuditoria
from .forms import calcular_imc


ETIQUETAS_SIGNOS = {
    'peso': ('Peso', 'kg'), 'talla': ('Talla', 'm'),
    'presion_arterial': ('Presión arterial', ''),
    'temperatura': ('Temperatura', '°C'), 'saturacion': ('Saturación', '%'),
    'frecuencia_cardiaca': ('Frecuencia cardíaca', 'lpm'), 'imc': ('IMC', ''),
}


def campos_de_preconsulta(es_menor):
    return ['peso', 'talla' if es_menor else 'presion_arterial',
            'temperatura', 'frecuencia_cardiaca', 'saturacion']


def valor_legible(campo, valor):
    if valor in (None, ''):
        return 'vacío'
    if isinstance(valor, Decimal):
        valor = f'{valor.normalize():f}'
    return f'{valor} {ETIQUETAS_SIGNOS[campo][1]}'.strip()


def corregir_signos(request, signos, datos, campos):
    """El llamador debe bloquear la Consulta dentro de transaction.atomic()."""
    cambios = []
    for campo in campos:
        anterior, nuevo = getattr(signos, campo), datos[campo]
        if (None if anterior == '' else anterior) != (None if nuevo == '' else nuevo):
            cambios.append((campo, anterior, nuevo))
            setattr(signos, campo, nuevo)
    if not cambios:
        return False
    anterior = signos.imc
    signos.imc = calcular_imc(signos.peso, signos.talla)
    if anterior != signos.imc:
        cambios.append(('imc', anterior, signos.imc))
    signos.modificado_por = request.user
    signos.save()
    persona = signos.consulta.expediente.persona
    registrar(request, RegistroAuditoria.Accion.EDITAR_PRECONSULTA,
              objetivo=f'{persona.nombres} {persona.apellidos}',
              detalle='; '.join(
                  f'{ETIQUETAS_SIGNOS[c][0]}: {valor_legible(c, a)} → {valor_legible(c, n)}'
                  for c, a, n in cambios))
    return True
