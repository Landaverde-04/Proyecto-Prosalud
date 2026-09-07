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


def generar_pdf(documento, borrador=False):
    consulta = documento.consulta
    clinica = consulta.expediente.clinica
    es_prosalud = 'prosalud' in clinica.nombre.lower().replace(' ', '').replace('-', '')
    encabezado = ENCABEZADO_PROSALUD if es_prosalud else {
        'nombre': clinica.nombre, 'direccion': clinica.direccion, 'telefono': clinica.telefono,
    }
    paciente_nombre = str(consulta.expediente.persona)
    doctor_nombre = documento.nombre_profesional
    doctor_jvpm = documento.jvpm_profesional
    salida = BytesIO()
    pdf = SimpleDocTemplate(salida, pagesize=letter, rightMargin=60, leftMargin=60,
                            topMargin=45, bottomMargin=55, title=documento.get_tipo_display(),
                            author=encabezado['nombre'])
    cuerpo = ParagraphStyle('Cuerpo', fontName='Times-Roman', fontSize=12, leading=19,
                            alignment=TA_JUSTIFY, spaceAfter=14, splitLongWords=True)
    centro = ParagraphStyle('Centro', parent=cuerpo, alignment=TA_CENTER, spaceAfter=4)
    titulo = ParagraphStyle('Titulo', parent=centro, fontName='Times-Bold', fontSize=15, leading=21)
    pequeno = ParagraphStyle('Pequeno', parent=centro, fontSize=9, leading=12)
    def seguro(valor):
        return escape(str(valor or '')).replace('\n', '<br/>')
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
    historia += [Spacer(1, 48), Paragraph('A QUIEN INTERESE:', cuerpo), Spacer(1, 8)]
    def relleno(valor):
        return '<u><b>'+seguro(valor)+'</b></u>'
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
    meses = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
             'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre')
    lugar = ' en la ciudad de Lourdes' if es_prosalud else ''
    anio = anio_en_letras(documento.fecha.year)
    expedicion = ('Y para los usos que el interesado estime conveniente se extiende la presente'
                  f'{lugar}, a los {relleno(documento.fecha.day)} días del mes de '
                  f'{relleno(meses[documento.fecha.month-1])} del año {anio}.')
    historia += [Spacer(1, 18), Paragraph(expedicion, cuerpo)]
    firma = [Spacer(1, 105), HRFlowable(width='75%', hAlign='CENTER', color=colors.black), Spacer(1, 7),
             Paragraph(seguro(doctor_nombre).upper(), centro)]
    if doctor_jvpm:
        firma.append(Paragraph('J.V.P.M. '+seguro(doctor_jvpm), centro))
    historia.append(KeepTogether(firma))
    def pie(canvas, doc):
        canvas.saveState();canvas.setFont('Helvetica',8);canvas.setFillColor(colors.grey)
        if borrador:
            canvas.drawString(60,30,'VISTA PREVIA · SIN EMITIR')
        canvas.restoreState()
    pdf.build(historia, onFirstPage=pie, onLaterPages=pie)
    return salida.getvalue()
