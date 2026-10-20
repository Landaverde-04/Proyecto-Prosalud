"""HU-EXP-22: PDF en memoria, usando las relaciones de la consulta."""
from io import BytesIO
from types import SimpleNamespace
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, KeepTogether,
                                HRFlowable, Table, TableStyle)

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


# Plantillas en blanco (HU-EXP-27): donde va un dato, una linea para
# escribirlo a mano. Tres largos, segun lo que se escribe ahi.
LINEA_CORTA = '_' * 8     # dias, numero del dia
LINEA_MEDIA = '_' * 22    # fechas, mes, especialidad
LINEA_LARGA = '_' * 48    # nombre del paciente, motivo, examenes


def documento_en_blanco(clinica, profesional):
    """
    Lo minimo que piden el membrete y la firma para dibujar una plantilla:
    la clinica y quien imprime. No es un registro y no se guarda en ningun
    lado -- imprimir una plantilla no crea folio ni toca la base
    (criterio 8 de HU-EXP-27).

    El membrete lleva el nombre y el J.V.P.M. de quien la imprime: es su
    papel, igual que en un documento emitido.
    """
    return SimpleNamespace(
        consulta=SimpleNamespace(expediente=SimpleNamespace(clinica=clinica)),
        nombre_profesional=profesional.get_full_name() or profesional.username,
        jvpm_profesional=getattr(profesional, 'jvpm', ''),
    )


def _estilos(plantilla=False):
    # En una plantilla el texto se llena a mano: el interlineado casi se
    # duplica para que quepa la letra sobre cada linea (criterio 5 de
    # HU-EXP-27: lineas mas altas que en el documento digital).
    # Y se alinea a la izquierda: justificado, las lineas largas para
    # escribir repartian el espacio y dejaban huecos enormes entre palabras.
    cuerpo = ParagraphStyle('Cuerpo', fontName='Times-Roman', fontSize=12,
                            leading=34 if plantilla else 19,
                            alignment=TA_LEFT if plantilla else TA_JUSTIFY,
                            spaceAfter=14, splitLongWords=True)
    centro = ParagraphStyle('Centro', parent=cuerpo, alignment=TA_CENTER, spaceAfter=4)
    return {'cuerpo': cuerpo, 'centro': centro,
            'titulo': ParagraphStyle('Titulo', parent=centro, fontName='Times-Bold', fontSize=15, leading=21),
            'pequeno': ParagraphStyle('Pequeno', parent=centro, fontSize=9, leading=12)}


def _abrir(documento, titulo_pdf, plantilla=False):
    """
    Abre el PDF y le pone el membrete. Comun a la constancia (HU-EXP-22), la
    referencia (HU-EXP-23) y la orden de examenes (HU-EXP-20).

    Desde el 21/09/2026 usa el MISMO membrete que la receta -- logo a la
    izquierda, medico y direccion a la derecha. Antes iba centrado, copiando
    el impreso viejo de la constancia, y los documentos no se parecian entre
    si. Decision de Samuel: que los cuatro se vean de la misma familia.

    Lo que NO se unifica son los recuadros redondeados: esos son de la
    receta. La constancia sigue siendo un parrafo corrido, que es lo que es.
    """
    clinica = documento.consulta.expediente.clinica
    es_prosalud = 'prosalud' in clinica.nombre.lower().replace(' ', '').replace('-', '')
    encabezado = ENCABEZADO_PROSALUD if es_prosalud else {
        'nombre': clinica.nombre, 'direccion': clinica.direccion, 'telefono': clinica.telefono,
    }
    salida = BytesIO()
    pdf = SimpleDocTemplate(salida, pagesize=letter, rightMargin=60, leftMargin=60,
                            topMargin=45, bottomMargin=55, title=titulo_pdf,
                            author=encabezado['nombre'])
    estilos = _estilos(plantilla)
    # Sin recuadro alrededor, el membrete ocupa todo el ancho util de la
    # hoja (612pt de carta menos los dos margenes de 60).
    historia = _membrete(documento, estilos, ancho_logo=170, ancho_datos=322)
    return salida, pdf, historia, estilos, es_prosalud


def _firma(documento, estilos):
    """
    Firma al pie: la raya en blanco y la palabra "Firma", sin partirse entre
    dos paginas.

    El nombre y el JVPM ya NO van aqui (21/09/2026). Desde que el membrete
    los lleva arriba, repetirlos abajo sobra -- es la misma correccion que
    Samuel pidio en la receta: "la informacion de la dra en la parte de
    abajo es muy redundante".

    La linea queda vacia a proposito: ahi firma y sella de puno y letra.

    Mas corta y con menos aire encima desde el 19/10/2026 (antes 75% y 105
    puntos): Samuel la veia demasiado grande. Los 75 puntos (~2,6 cm) siguen
    dejando sitio para el sello.
    """
    pie = ParagraphStyle('Firma', parent=estilos['centro'], fontSize=9, leading=13)
    return KeepTogether([
        Spacer(1, 75),
        HRFlowable(width='42%', hAlign='CENTER', color=colors.black),
        Spacer(1, 4),
        Paragraph('Firma', pie),
    ])


def _pie_borrador(borrador):
    def pie(canvas, doc):
        canvas.saveState(); canvas.setFont('Helvetica', 8); canvas.setFillColor(colors.grey)
        if borrador:
            canvas.drawString(60, 30, 'VISTA PREVIA \u00b7 SIN EMITIR')
        canvas.restoreState()
    return pie


def _expedicion(documento, estilos, es_prosalud, plantilla=False):
    """Parrafo de cierre, con el ano en letras de la fecha de emision."""
    meses = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
             'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre')
    lugar = ' en la ciudad de Lourdes' if es_prosalud else ''
    if plantilla:
        return Paragraph('Y para los usos que el interesado estime conveniente se extiende la '
                         f'presente{lugar}, a los {LINEA_CORTA} d\u00edas del mes de {LINEA_MEDIA} '
                         f'del a\u00f1o {LINEA_MEDIA}.', estilos['cuerpo'])
    texto = ('Y para los usos que el interesado estime conveniente se extiende la presente'
             f'{lugar}, a los {relleno(documento.fecha.day)} d\u00edas del mes de '
             f'{relleno(meses[documento.fecha.month-1])} del a\u00f1o {anio_en_letras(documento.fecha.year)}.')
    return Paragraph(texto, estilos['cuerpo'])


def generar_pdf(documento, borrador=False, plantilla=False):
    """
    Constancia de incapacidad (HU-EXP-22).

    Con `plantilla=True` dibuja la misma constancia en blanco, con lineas
    donde van los datos (HU-EXP-27). Es la misma funcion a proposito: si
    cambia el formato de la constancia, su plantilla cambia con ella.
    """
    doctor_nombre = documento.nombre_profesional
    titulo = 'Constancia de incapacidad' if plantilla else documento.get_tipo_display()
    salida, pdf, historia, estilos, es_prosalud = _abrir(documento, titulo, plantilla)
    cuerpo, centro = estilos['cuerpo'], estilos['centro']
    historia += [Spacer(1, 48), Paragraph('A QUIEN INTERESE:', cuerpo), Spacer(1, 8)]
    paciente = LINEA_LARGA if plantilla else relleno(str(documento.consulta.expediente.persona))
    texto = (f'EL INFRASCRITO MÉDICO, {seguro(doctor_nombre)}, por medio de la presente, '
             f'HACE CONSTAR QUE {paciente} ')
    if plantilla:
        texto += (f'adolece de {LINEA_LARGA}, por lo que amerita {LINEA_CORTA} días de '
                  f'incapacidad con tratamiento a partir del {LINEA_MEDIA} hasta el '
                  f'{LINEA_MEDIA}.')
    elif documento.tipo == Incapacidad.Tipo.INCAPACIDAD:
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
    historia += [Spacer(1, 18), _expedicion(documento, estilos, es_prosalud, plantilla)]
    historia.append(_firma(documento, estilos))
    pdf.build(historia, onFirstPage=_pie_borrador(borrador), onLaterPages=_pie_borrador(borrador))
    return salida.getvalue()


def generar_pdf_referencia(referencia, borrador=False, plantilla=False):
    """
    Referencia medica (HU-EXP-23). Reusa el encabezado, la expedicion y la
    firma de la constancia: es el mismo papel de la clinica.

    El texto lo dicto la doctora el 09/10/2026 (CD-06):

        "...refiere a [paciente] a la especialidad de [X] del hospital [Y],
        por el siguiente motivo: [motivo], para evaluacion y tratamiento."

    Antes era provisional: no habia un impreso real de referencia que copiar.

    Con `plantilla=True`, la misma referencia en blanco (HU-EXP-27).
    """
    salida, pdf, historia, estilos, es_prosalud = _abrir(referencia, 'Referencia medica', plantilla)
    cuerpo = estilos['cuerpo']
    # Mismo esqueleto que la constancia: encabezado, "A QUIEN INTERESE", un
    # parrafo corrido con los datos subrayados, expedicion y firma. Es el
    # papel de la clinica, no un formato propio de cada documento.
    historia += [Spacer(1, 48), Paragraph('A QUIEN INTERESE:', cuerpo), Spacer(1, 8)]
    if plantilla:
        texto = (f'EL INFRASCRITO MÉDICO, {seguro(referencia.nombre_profesional)}, por medio de '
                 f'la presente, REFIERE A {LINEA_LARGA} a la especialidad de {LINEA_MEDIA} del '
                 f'hospital {LINEA_LARGA}, por el siguiente motivo: {LINEA_LARGA}, para '
                 f'evaluación y tratamiento.')
        historia.append(Paragraph(texto, cuerpo))
        historia += [Spacer(1, 18), _expedicion(referencia, estilos, es_prosalud, plantilla)]
        historia.append(_firma(referencia, estilos))
        pdf.build(historia)
        return salida.getvalue()
    paciente = str(referencia.consulta.expediente.persona)
    destino = relleno(referencia.especialidad)
    # El hospital es opcional: sin el, la frase queda como antes en vez de
    # decir "del hospital" seguido de un hueco.
    if referencia.hospital:
        # Si la doctora escribio el nombre completo ("Hospital Rosales"), no
        # se repite la palabra: quedaria "del hospital Hospital Rosales".
        if referencia.hospital.lower().startswith('hospital'):
            destino += f' del {relleno(referencia.hospital)}'
        else:
            destino += f' del hospital {relleno(referencia.hospital)}'
    # El punto final lo pone la frase fija; si la doctora termino el motivo
    # con punto, sin esto quedaria "dolor abdominal., para evaluacion".
    motivo = referencia.motivo.strip().rstrip('.')
    texto = (f'EL INFRASCRITO MÉDICO, {seguro(referencia.nombre_profesional)}, por medio de la '
             f'presente, REFIERE A {relleno(paciente)} a la especialidad de {destino}, '
             f'por el siguiente motivo: {relleno(motivo)}, para evaluación y tratamiento.')
    # Las observaciones van despues de la frase fija, para que esta cierre
    # la referencia propiamente dicha.
    if referencia.observaciones:
        texto += f' Observaciones: {relleno(referencia.observaciones)}.'
    historia.append(Paragraph(texto, cuerpo))
    historia += [Spacer(1, 18), _expedicion(referencia, estilos, es_prosalud)]
    historia.append(_firma(referencia, estilos))
    pdf.build(historia, onFirstPage=_pie_borrador(borrador), onLaterPages=_pie_borrador(borrador))
    return salida.getvalue()


def generar_pdf_orden(orden, borrador=False, plantilla=False):
    """
    Orden de examenes (HU-EXP-20). Mismo papel de la clinica que los demas
    documentos: encabezado, parrafo corrido, expedicion y firma.

    Version sencilla acordada con Samuel el 21/09/2026: los examenes y las
    indicaciones, nada mas. El detalle por tipo de examen llegara con el
    modulo de Laboratorio.

    Con `plantilla=True`, la misma orden en blanco (HU-EXP-27), con espacio
    para varios examenes y para las indicaciones.
    """
    salida, pdf, historia, estilos, es_prosalud = _abrir(orden, 'Orden de examenes', plantilla)
    cuerpo = estilos['cuerpo']
    historia += [Spacer(1, 48), Paragraph('A QUIEN INTERESE:', cuerpo), Spacer(1, 8)]
    if plantilla:
        texto = (f'EL INFRASCRITO MÉDICO, {seguro(orden.nombre_profesional)}, por medio de la '
                 f'presente, SOLICITA que a {LINEA_LARGA} le sean realizados los siguientes '
                 f'exámenes: {LINEA_LARGA} {LINEA_LARGA}. Indicaciones: {LINEA_LARGA}.')
    else:
        paciente = str(orden.persona)
        examenes = ', '.join(d.tipo_examen for d in orden.detalles.filter(activo=True))
        texto = (f'EL INFRASCRITO MÉDICO, {seguro(orden.nombre_profesional)}, por medio de la '
                 f'presente, SOLICITA que a {relleno(paciente)} le sean realizados los '
                 f'siguientes exámenes: {relleno(examenes)}.')
        if orden.indicaciones:
            texto += f' Indicaciones: {relleno(orden.indicaciones)}.'
    historia.append(Paragraph(texto, cuerpo))
    historia += [Spacer(1, 18), _expedicion(orden, estilos, es_prosalud, plantilla)]
    historia.append(_firma(orden, estilos))
    pdf.build(historia, onFirstPage=_pie_borrador(borrador), onLaterPages=_pie_borrador(borrador))
    return salida.getvalue()


def _membrete(documento, estilos, ancho_logo=160, ancho_datos=300):
    """
    Membrete de TODOS los documentos, copiado de la receta real que dio
    Samuel (21/09/2026): el logo solo, a la izquierda, y a su derecha un
    bloque con el medico y los datos de contacto, uno debajo de otro y
    alineados a la izquierda -- no centrados.

        [ logo ]   ELSA CECILIA MIRANDA VELASQUEZ
                   Medicina general
                   Cel. 7629-2725
                   Calle Francisco Menendez # 2-9
                   Frente a Unidad de Salud de Lourdes, Colon

    Nacio para la receta y el 21/09/2026 paso a usarlo tambien `_abrir`,
    para que los cuatro documentos se vean de la misma familia. `ancho_logo`
    y `ancho_datos` existen porque dentro del recuadro de la receta cabe
    menos que en la hoja abierta de la constancia.
    """
    clinica = documento.consulta.expediente.clinica
    es_prosalud = 'prosalud' in clinica.nombre.lower().replace(' ', '').replace('-', '')
    encabezado = ENCABEZADO_PROSALUD if es_prosalud else {
        'nombre': clinica.nombre, 'direccion': clinica.direccion, 'telefono': clinica.telefono,
    }
    cuerpo = estilos['cuerpo']
    chico = ParagraphStyle('Chico', parent=cuerpo, alignment=TA_LEFT, fontSize=8,
                           leading=11, spaceAfter=0)
    nombre = ParagraphStyle('NombreMed', parent=cuerpo, alignment=TA_LEFT, fontSize=14,
                            leading=18, spaceAfter=0)
    dato = ParagraphStyle('Dato', parent=cuerpo, alignment=TA_LEFT, fontSize=9,
                          leading=13, spaceAfter=0)

    if es_prosalud:
        logo = [Paragraph('CLÍNICA', chico),
                Paragraph('<font color="#1a7a4c">PR<font face="ZapfDingbats" color="#c0392b">\u2764</font>SALUD</font>',
                          ParagraphStyle('LogoIzq', parent=chico, fontName='Helvetica-Bold',
                                         fontSize=22, leading=26)),
                Paragraph('CONSULTA MÉDICA<br/>ODONTOLOGÍA Y LABORATORIO', chico)]
    else:
        logo = [Paragraph(seguro(encabezado['nombre']),
                          ParagraphStyle('NombreClinica', parent=chico, fontName='Times-Bold',
                                         fontSize=14, leading=18))]

    # A la derecha, todo el bloque del medico, como en la referencia.
    datos = [Paragraph(seguro(documento.nombre_profesional).upper(), nombre)]
    datos.append(Paragraph('Medicina general' if es_prosalud
                           else seguro(clinica.get_tipo_display()), dato))
    if documento.jvpm_profesional:
        datos.append(Paragraph('J.V.P.M. ' + seguro(documento.jvpm_profesional), dato))
    if encabezado['telefono']:
        datos.append(Paragraph('Cel. ' + seguro(encabezado['telefono']), dato))
    if encabezado['direccion']:
        datos.append(Paragraph(seguro(encabezado['direccion'].title()), dato))

    return [Table([[logo, datos]], colWidths=[ancho_logo, ancho_datos], style=TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('LEFTPADDING', (1, 0), (1, 0), 14),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ])),
        Spacer(1, 12),
        HRFlowable(width='100%', color=colors.HexColor('#999999'), thickness=0.6)]


def generar_pdf_receta(receta, borrador=False, plantilla=False):
    """
    Receta medica (HU-EXP-25).

    NO sigue el esqueleto de la constancia. Una receta no le hace constar
    nada a nadie: es una indicacion para la farmacia y para el paciente, asi
    que no lleva "A QUIEN INTERESE" ni el parrafo de expedicion.

    La estructura sale de la referencia que dio Samuel el 21/09/2026: dos
    recuadros de esquinas redondeadas, uno con el membrete y lo recetado, y
    otro con quien la recibe.

        .-----------------------------------------------.
        |  [logo]   NOMBRE DE LA MEDICA                 |
        |           especialidad, JVPM, telefono        |
        |           direccion                           |
        |  -------------------------------------------  |
        |  Nombre del paciente: ________  Fecha: _____  |
        |                                               |
        |   Nombre del medicamento                      |
        |   Uso: dosis                       duracion   |
        '-----------------------------------------------'

        .-----------------------------------------------.
        |              ____________________             |
        |                     Firma                     |
        '-----------------------------------------------'

    El paciente va ARRIBA, junto a la fecha, debajo del membrete: pedido de
    la doctora del 09/10/2026 (CD-02). Hasta entonces iba en el recuadro de
    abajo. Bajo la linea de firma solo va la palabra "Firma": el nombre y el
    JVPM de la medica ya estan en el membrete.

    Con `plantilla=True`, la misma receta en blanco (HU-EXP-27): los
    renglones de paciente y fecha vacios y mas altos, y el recuadro de los
    medicamentos libre para escribir a mano.
    """
    paciente = '' if plantilla else str(receta.consulta.expediente.persona)
    fecha_texto = '' if plantilla else receta.fecha.strftime('%d/%m/%Y')
    # `_abrir` deja el membrete en `historia`; aqui va DENTRO del recuadro,
    # como en la referencia, en vez de suelto arriba de la hoja.
    # Se descarta el membrete centrado de `_abrir`: la receta usa el suyo.
    salida, pdf, _, estilos, es_prosalud = _abrir(receta, 'Receta medica', plantilla)
    membrete = _membrete(receta, estilos)
    cuerpo = estilos['cuerpo']
    ANCHO = 492

    def recuadro(contenido, alto_minimo=None):
        """Un bloque con borde y esquinas redondeadas, como los de la referencia."""
        estilo = [('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor('#555555')),
                  ('ROUNDEDCORNERS', [10, 10, 10, 10]),
                  # Sin esto el contenido se va al fondo del recuadro.
                  ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                  ('LEFTPADDING', (0, 0), (-1, -1), 16),
                  ('RIGHTPADDING', (0, 0), (-1, -1), 16),
                  ('TOPPADDING', (0, 0), (-1, -1), 14),
                  ('BOTTOMPADDING', (0, 0), (-1, -1), 14)]
        return Table([[contenido]], colWidths=[ANCHO],
                     rowHeights=[alto_minimo] if alto_minimo else None,
                     style=TableStyle(estilo))

    # --- Recuadro de lo recetado ---
    nombre = ParagraphStyle('Med', parent=cuerpo, fontName='Times-Bold', fontSize=13,
                            leading=17, spaceAfter=2)
    uso = ParagraphStyle('Uso', parent=cuerpo, fontSize=12, leading=17, spaceAfter=0)
    derecha = ParagraphStyle('Cantidad', parent=cuerpo, alignment=TA_RIGHT, fontSize=12, leading=17)
    linea = ParagraphStyle('Renglon', parent=cuerpo, fontSize=11, leading=15,
                           alignment=TA_LEFT, spaceAfter=0)
    firma = ParagraphStyle('Firma', parent=cuerpo, alignment=TA_CENTER, fontSize=9,
                           leading=13, spaceAfter=0)

    # Paciente y fecha en UNA linea, con renglon para escribir debajo de cada
    # dato aunque venga impreso: cuando exista el apartado de plantillas
    # (HU-EXP-27), este mismo formato se imprime en blanco y se llena a mano.
    # Las cuatro columnas suman los 460 puntos utiles dentro del recuadro.
    paciente_y_fecha = Table(
        [[Paragraph('Nombre del paciente:', linea), Paragraph(seguro(paciente), linea),
          Paragraph('Fecha:', linea), Paragraph(seguro(fecha_texto), linea)]],
        colWidths=[112, 214, 44, 90], style=TableStyle([
            # La linea va solo bajo los datos, no bajo las etiquetas.
            ('LINEBELOW', (1, 0), (1, 0), 0.7, colors.black),
            ('LINEBELOW', (3, 0), (3, 0), 0.7, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING', (2, 0), (2, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            # En la plantilla el renglon se llena a mano: mas alto.
            ('TOPPADDING', (0, 0), (-1, -1), 18 if plantilla else 3),
        ]))

    # El membrete abre el recuadro; debajo, quien recibe la receta y la
    # fecha; despues, lo recetado.
    recetado = membrete + [Spacer(1, 16), paciente_y_fecha, Spacer(1, 20)]
    # En la plantilla el recuadro queda vacio: ahi se escribe la receta.
    detalles = [] if plantilla else receta.detalles.filter(activo=True)
    for detalle in detalles:
        recetado.append(Table(
            [[Paragraph(seguro(detalle.medicamento), nombre), ''],
             [Paragraph('Uso: ' + seguro(detalle.dosis), uso),
              Paragraph(seguro(detalle.duracion), derecha)]],
            colWidths=[300, 160], style=TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (-1, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('SPAN', (0, 0), (1, 0)),
            ])))
        recetado.append(Spacer(1, 16))
    if not plantilla and receta.consulta.indicaciones:
        recetado.append(Paragraph('<b>Indicaciones:</b> ' + seguro(receta.consulta.indicaciones), cuerpo))

    # Alto minimo para que el recuadro no se vea apretado con un solo
    # medicamento, y para dejar sitio a la letra de la doctora si anota algo.
    # Es mas alto que antes (480) porque el recuadro de abajo se achico al
    # quedarse solo con la firma.
    historia = [recuadro(recetado, alto_minimo=530), Spacer(1, 18)]

    # --- Recuadro de la firma ---
    firma_bloque = [
        Spacer(1, 28),
        # La linea queda en blanco: ahi firma y sella de puno y letra. Va
        # dentro de una tabla porque `hAlign` de HRFlowable no centra dentro
        # de otra tabla -- la dejaba pegada a la izquierda.
        Table([['', '', '']], colWidths=[135, 190, 135], rowHeights=[1],
              style=TableStyle([
                  ('LINEBELOW', (1, 0), (1, 0), 0.8, colors.black),
                  ('LEFTPADDING', (0, 0), (-1, -1), 0),
                  ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                  ('TOPPADDING', (0, 0), (-1, -1), 0),
                  ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
              ])),
        Spacer(1, 4),
        # Solo la etiqueta: el nombre y el JVPM de la medica ya estan en el
        # membrete; la firma misma es el nombre.
        Paragraph('Firma', firma),
    ]
    historia.append(KeepTogether(recuadro(firma_bloque)))

    pdf.build(historia, onFirstPage=_pie_borrador(borrador), onLaterPages=_pie_borrador(borrador))
    return salida.getvalue()
