"""HU-EXP-22: PDF en memoria, a partir de los datos conservados al emitir."""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether, HRFlowable

from .models import Incapacidad



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
    salida = BytesIO()
    pdf = SimpleDocTemplate(salida, pagesize=letter, rightMargin=60, leftMargin=60,
                            topMargin=45, bottomMargin=55, title=documento.get_tipo_display(),
                            author=documento.clinica_nombre)
    cuerpo = ParagraphStyle('Cuerpo', fontName='Times-Roman', fontSize=12, leading=19,
                            alignment=TA_JUSTIFY, spaceAfter=14, splitLongWords=True)
    centro = ParagraphStyle('Centro', parent=cuerpo, alignment=TA_CENTER, spaceAfter=4)
    titulo = ParagraphStyle('Titulo', parent=centro, fontName='Times-Bold', fontSize=15, leading=21)
    pequeno = ParagraphStyle('Pequeno', parent=centro, fontSize=9, leading=12)
    def seguro(valor):
        return escape(str(valor or '')).replace('\n', '<br/>')
    historia = []
    # Logo tipográfico recreado del mockup; no usa la imagen de baja resolución.
    if 'prosalud' in documento.clinica_nombre.lower().replace(' ', ''):
        historia += [Paragraph('CLÍNICA', pequeno),
                     Paragraph('<font color="#1a7a4c">PR<font face="ZapfDingbats" color="#c0392b">\u2764</font>SALUD</font>',
                               ParagraphStyle('Logo', parent=centro, fontName='Helvetica-Bold', fontSize=25, leading=29)),
                     Paragraph('CONSULTA MÉDICA<br/>ODONTOLOGÍA Y LABORATORIO', pequeno)]
    else:
        historia.append(Paragraph(seguro(documento.clinica_nombre), titulo))
    historia += [Spacer(1, 18), Paragraph(seguro(documento.doctor_nombre).upper(), centro)]
    if 'prosalud' in documento.clinica_nombre.lower().replace(' ', ''):
        historia.append(Paragraph('MEDICINA GENERAL', centro))
    historia.append(Spacer(1, 12))
    if documento.clinica_direccion:
        historia.append(Paragraph(seguro(documento.clinica_direccion), pequeno))
    if documento.clinica_telefono:
        historia.append(Paragraph('CEL. '+seguro(documento.clinica_telefono), pequeno))
    historia += [Spacer(1, 48), Paragraph('A QUIEN INTERESE:', cuerpo), Spacer(1, 8)]
    def relleno(valor):
        return '<u><b>'+seguro(valor)+'</b></u>'
    texto = (f'EL INFRASCRITO MÉDICO, {seguro(documento.doctor_nombre)}, por medio de la presente, '
             f'HACE CONSTAR QUE {relleno(documento.paciente_nombre)} ')
    if documento.tipo == Incapacidad.Tipo.INCAPACIDAD:
        texto += (f'adolece de {relleno(documento.motivo)}, por lo que amerita '
                  f'{relleno(documento.dias)} {"día" if documento.dias == 1 else "días"} '
                  f'de incapacidad con tratamiento a partir del '
                  f'{relleno(documento.fecha_inicio.strftime("%d/%m/%Y"))} hasta el '
                  f'{relleno(documento.fecha_fin.strftime("%d/%m/%Y"))}.')
    else:
        fecha = documento.fecha_atencion.strftime('%d/%m/%Y') if documento.fecha_atencion else 'No registrada'
        texto += (f'recibió atención médica el {relleno(fecha)}, por el siguiente motivo: '
                  f'{relleno(documento.motivo)}.')
    historia.append(Paragraph(texto, cuerpo))
    meses = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
             'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre')
    lugar = ' en la ciudad de Lourdes' if 'prosalud' in documento.clinica_nombre.lower().replace(' ', '') else ''
    anio = anio_en_letras(documento.fecha.year)
    expedicion = ('Y para los usos que el interesado estime conveniente se extiende la presente'
                  f'{lugar}, a los {relleno(documento.fecha.day)} días del mes de '
                  f'{relleno(meses[documento.fecha.month-1])} del año {anio}.')
    historia += [Spacer(1, 18), Paragraph(expedicion, cuerpo)]
    firma = [Spacer(1, 105), HRFlowable(width='75%', hAlign='CENTER', color=colors.black), Spacer(1, 7),
             Paragraph(seguro(documento.doctor_nombre).upper(), centro)]
    if documento.doctor_jvpm:
        firma.append(Paragraph('J.V.P.M. '+seguro(documento.doctor_jvpm), centro))
    historia.append(KeepTogether(firma))
    def pie(canvas, doc):
        canvas.saveState();canvas.setFont('Helvetica',8);canvas.setFillColor(colors.grey)
        if borrador:
            canvas.drawString(60,30,'VISTA PREVIA · SIN EMITIR')
        canvas.restoreState()
    pdf.build(historia, onFirstPage=pie, onLaterPages=pie)
    return salida.getvalue()
