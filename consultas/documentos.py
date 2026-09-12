"""HU-EXP-22: PDF en memoria, usando las relaciones de la consulta."""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether, HRFlowable

from .models import Incapacidad


# Datos fijos del impreso de ProSalud; no se copian en cada incapacidad.
ENCABEZADO_PROSALUD = {
    'nombre': 'Clínica ProSalud',
    'direccion': 'CALLE FRANCISCO MENENDEZ # 2-9\nFRENTE A UNIDAD DE SALUD DE LOURDES, COLON',
    'telefono': '7629-2725',
}



def anio_en_letras(anio):
    """Expresa el año de emisión, sin depender del año actual del servidor."""
    unidades = ('cero', 'uno', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho', 'nueve')
    especiales = ('diez', 'once', 'doce', 'trece', 'catorce', 'quince', 'dieciséis',
                  'diecisiete', 'dieciocho', 'diecinueve', 'veinte', 'veintiuno',
                  'veintidós', 'veintitrés', 'veinticuatro', 'veinticinco', 'veintiséis',
                  'veintisiete', 'veintiocho', 'veintinueve')
    decenas = ('', '', '', 'treinta', 'cuarenta', 'cincuenta', 'sesenta', 'setenta', 'ochenta', 'noventa')
    centenas = ('', 'ciento', 'doscientos', 'trescientos', 'cuatrocientos', 'quinientos',
                'seiscientos', 'setecientos', 'ochocientos', 'novecientos')
    if anio < 10:
        return unidades[anio]
    if anio < 30:
        return especiales[anio-10]
    if anio < 100:
        return decenas[anio//10] + (' y '+unidades[anio%10] if anio%10 else '')
    if anio == 100:
        return 'cien'
    if anio < 1000:
        return centenas[anio//100] + (' '+anio_en_letras(anio%100) if anio%100 else '')
    miles, resto = divmod(anio, 1000)
    return ('mil' if miles == 1 else unidades[miles]+' mil') + (' '+anio_en_letras(resto) if resto else '')


def seguro(valor):
    """Lo que escribe la doctora se imprime como contenido, no como formato."""
    return escape(str(valor or '')).replace('\n', '<br/>')


def relleno(valor):
    """Los datos variables van subrayados, como en el impreso de la clinica."""
    return '<u><b>' + seguro(valor) + '</b></u>'


def _estilos():
    cuerpo = ParagraphStyle('Cuerpo', fontName='Times-Roman', fontSize=12, leading=19,
                            alignment=TA_JUSTIFY, spaceAfter=14, splitLongWords=True)
    centro = ParagraphStyle('Centro', parent=cuerpo, alignment=TA_CENTER, spaceAfter=4)
    return {'cuerpo': cuerpo, 'centro': centro,
            'titulo': ParagraphStyle('Titulo', parent=centro, fontName='Times-Bold', fontSize=15, leading=21),
            'pequeno': ParagraphStyle('Pequeno', parent=centro, fontSize=9, leading=12)}


def _abrir(documento, titulo_pdf):
    """
    Encabezado comun a los documentos de la consulta: logo, nombre del medico
    y datos de la clinica. Lo comparten la constancia de incapacidad
    (HU-EXP-22) y la referencia medica (HU-EXP-23), y lo reusaran los que
    falten -- asi el papel de la clinica se define en un solo lugar.
    """
    clinica = documento.consulta.expediente.clinica
    es_prosalud = 'prosalud' in clinica.nombre.lower().replace(' ', '').replace('-', '')
    encabezado = ENCABEZADO_PROSALUD if es_prosalud else {
        'nombre': clinica.nombre, 'direccion': clinica.direccion, 'telefono': clinica.telefono,
    }
    doctor_nombre = documento.nombre_profesional
    salida = BytesIO()
    pdf = SimpleDocTemplate(salida, pagesize=letter, rightMargin=60, leftMargin=60,
                            topMargin=45, bottomMargin=55, title=titulo_pdf,
                            author=encabezado['nombre'])
    estilos = _estilos()
    cuerpo, centro = estilos['cuerpo'], estilos['centro']
    titulo, pequeno = estilos['titulo'], estilos['pequeno']
    historia = []
    # Logo tipográfico recreado del mockup; no usa la imagen de baja resolución.
    if es_prosalud:
        historia += [Paragraph('CLÍNICA', pequeno),
                     Paragraph('<font color="#1a7a4c">PR<font face="ZapfDingbats" color="#c0392b">\u2764</font>SALUD</font>',
                               ParagraphStyle('Logo', parent=centro, fontName='Helvetica-Bold', fontSize=25, leading=29)),
                     Paragraph('CONSULTA MÉDICA<br/>ODONTOLOGÍA Y LABORATORIO', pequeno)]
    else:
        historia.append(Paragraph(seguro(encabezado['nombre']), titulo))
    historia += [Spacer(1, 18), Paragraph(seguro(doctor_nombre).upper(), centro)]
    if es_prosalud:
        historia.append(Paragraph('MEDICINA GENERAL', centro))
    historia.append(Spacer(1, 12))
    if encabezado['direccion']:
        historia.append(Paragraph(seguro(encabezado['direccion']), pequeno))
    if encabezado['telefono']:
        historia.append(Paragraph('CEL. '+seguro(encabezado['telefono']), pequeno))
    return salida, pdf, historia, estilos, es_prosalud


def _firma(documento, estilos):
    """Firma al pie: raya, nombre y JVPM, sin partirse entre dos paginas."""
    centro = estilos['centro']
    bloque = [Spacer(1, 105), HRFlowable(width='75%', hAlign='CENTER', color=colors.black),
              Spacer(1, 7), Paragraph(seguro(documento.nombre_profesional).upper(), centro)]
    if documento.jvpm_profesional:
        bloque.append(Paragraph('J.V.P.M. ' + seguro(documento.jvpm_profesional), centro))
    return KeepTogether(bloque)


def _pie_borrador(borrador):
    def pie(canvas, doc):
        canvas.saveState(); canvas.setFont('Helvetica', 8); canvas.setFillColor(colors.grey)
        if borrador:
            canvas.drawString(60, 30, 'VISTA PREVIA \u00b7 SIN EMITIR')
        canvas.restoreState()
    return pie


def _expedicion(documento, estilos, es_prosalud):
    """Parrafo de cierre, con el ano en letras de la fecha de emision."""
    meses = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
             'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre')
    lugar = ' en la ciudad de Lourdes' if es_prosalud else ''
    texto = ('Y para los usos que el interesado estime conveniente se extiende la presente'
             f'{lugar}, a los {relleno(documento.fecha.day)} d\u00edas del mes de '
             f'{relleno(meses[documento.fecha.month-1])} del a\u00f1o {anio_en_letras(documento.fecha.year)}.')
    return Paragraph(texto, estilos['cuerpo'])


def generar_pdf(documento, borrador=False):
    """Constancia de incapacidad (HU-EXP-22)."""
    paciente_nombre = str(documento.consulta.expediente.persona)
    doctor_nombre = documento.nombre_profesional
    salida, pdf, historia, estilos, es_prosalud = _abrir(documento, documento.get_tipo_display())
    cuerpo, centro = estilos['cuerpo'], estilos['centro']
    historia += [Spacer(1, 48), Paragraph('A QUIEN INTERESE:', cuerpo), Spacer(1, 8)]
    texto = (f'EL INFRASCRITO MÉDICO, {seguro(doctor_nombre)}, por medio de la presente, '
             f'HACE CONSTAR QUE {relleno(paciente_nombre)} ')
    if documento.tipo == Incapacidad.Tipo.INCAPACIDAD:
        texto += (f'adolece de {relleno(documento.motivo)}, por lo que amerita '
                  f'{relleno(documento.dias)} {"día" if documento.dias == 1 else "días"} '
                  f'de incapacidad con tratamiento a partir del '
                  f'{relleno(documento.fecha_inicio_incapacidad.strftime("%d/%m/%Y"))} hasta el '
                  f'{relleno(documento.fecha_fin.strftime("%d/%m/%Y"))}.')
    else:
        fecha = documento.fecha_atencion.strftime('%d/%m/%Y') if documento.fecha_atencion else 'No registrada'
        texto += (f'recibió atención médica el {relleno(fecha)}, por el siguiente motivo: '
                  f'{relleno(documento.motivo)}.')
    historia.append(Paragraph(texto, cuerpo))
    historia += [Spacer(1, 18), _expedicion(documento, estilos, es_prosalud)]
    historia.append(_firma(documento, estilos))
    pdf.build(historia, onFirstPage=_pie_borrador(borrador), onLaterPages=_pie_borrador(borrador))
    return salida.getvalue()


def generar_pdf_referencia(referencia, borrador=False):
    """
    Referencia medica (HU-EXP-23). Reusa el encabezado, la expedicion y la
    firma de la constancia: es el mismo papel de la clinica.

    El formato del texto es provisional -- no existe un impreso real de
    referencia como el que se uso para la constancia. Falta aprobarlo con
    la doctora.
    """
    paciente = str(referencia.consulta.expediente.persona)
    salida, pdf, historia, estilos, es_prosalud = _abrir(referencia, 'Referencia medica')
    cuerpo = estilos['cuerpo']
    # Mismo esqueleto que la constancia: encabezado, "A QUIEN INTERESE", un
    # parrafo corrido con los datos subrayados, expedicion y firma. Es el
    # papel de la clinica, no un formato propio de cada documento.
    historia += [Spacer(1, 48), Paragraph('A QUIEN INTERESE:', cuerpo), Spacer(1, 8)]
    texto = (f'EL INFRASCRITO MÉDICO, {seguro(referencia.nombre_profesional)}, por medio de la '
             f'presente, REFIERE A {relleno(paciente)} a la especialidad de '
             f'{relleno(referencia.especialidad)}, por el siguiente motivo: '
             f'{relleno(referencia.motivo)}.')
    if referencia.observaciones:
        texto += f' Observaciones: {relleno(referencia.observaciones)}.'
    historia.append(Paragraph(texto, cuerpo))
    historia += [Spacer(1, 18), _expedicion(referencia, estilos, es_prosalud)]
    historia.append(_firma(referencia, estilos))
    pdf.build(historia, onFirstPage=_pie_borrador(borrador), onLaterPages=_pie_borrador(borrador))
    return salida.getvalue()
