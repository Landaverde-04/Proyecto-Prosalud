"""
PDF de la atencion estetica (HU-EST-03), en memoria, con ReportLab.

Es propio de la Estetica: su membrete lleva el logo de la clinica y no el de
ProSalud. La figura con las zonas a tratar va en una sola pagina junto con la
lista de sus puntos (pedido de Samuel, 22/10/2026): si no cabe donde queda,
pasa entera a la pagina siguiente.
"""
import math
from io import BytesIO
from types import SimpleNamespace
from xml.sax.saxutils import escape

from django.contrib.staticfiles import finders
from django.utils import timezone
from PIL import Image as ImagenPIL
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (Flowable, HRFlowable, Image, KeepTogether, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

from .models import AtencionEstetica, ProcedimientoEstetico

ANCHO_UTIL = letter[0] - 2 * 54
ROJO = colors.HexColor('#c0392b')
GRIS = colors.HexColor('#999999')
FONDO_TITULO = colors.HexColor('#f4ece6')

IMAGENES = {
    AtencionEstetica.Figura.MUJER: 'estetica/img/figura_mujer.webp',
    AtencionEstetica.Figura.HOMBRE: 'estetica/img/figura_hombre.webp',
}


def seguro(valor):
    """Lo que escribe la doctora se imprime como contenido, no como formato."""
    return escape(str(valor or '')).replace('\n', '<br/>')


def _estilos():
    cuerpo = ParagraphStyle('Cuerpo', fontName='Helvetica', fontSize=10, leading=14,
                            alignment=TA_LEFT, spaceAfter=0, splitLongWords=True)
    return {
        'cuerpo': cuerpo,
        'titulo': ParagraphStyle('Titulo', parent=cuerpo, fontName='Helvetica-Bold', fontSize=15, leading=19),
        'seccion': ParagraphStyle('Seccion', parent=cuerpo, fontName='Helvetica-Bold', fontSize=9,
                                  leading=12, textColor=colors.HexColor('#6b5a4e')),
        'etiqueta': ParagraphStyle('Etiqueta', parent=cuerpo, fontSize=8, leading=10,
                                   textColor=colors.HexColor('#6b5a4e')),
        'medico': ParagraphStyle('Medico', parent=cuerpo, fontName='Helvetica-Bold', fontSize=12, leading=15),
        'dato': ParagraphStyle('Dato', parent=cuerpo, fontSize=9, leading=12),
    }


# Color de marca de la clinica estetica (el dorado del tema, estilos.css).
COLOR_LOGO = (162, 95, 42)


def _logo_para_papel(ruta):
    """
    El logo del sistema es claro, hecho para el menu oscuro: en una hoja
    blanca casi no se ve. Se tine en memoria con el color de la clinica,
    conservando su forma (canal alfa); no se guarda ningun archivo.
    """
    original = ImagenPIL.open(ruta).convert('RGBA')
    tenido = ImagenPIL.new('RGBA', original.size, COLOR_LOGO + (0,))
    tenido.putalpha(original.getchannel('A'))
    salida = BytesIO()
    tenido.save(salida, format='PNG')
    salida.seek(0)
    return salida, original.size


def _membrete(atencion, estilos):
    """Logo de la clinica a la izquierda; la doctora y los datos de contacto a la derecha."""
    clinica = atencion.expediente.clinica
    ruta_logo = finders.find(clinica.logo) if clinica.logo else None
    if ruta_logo:
        archivo, (ancho_img, alto_img) = _logo_para_papel(ruta_logo)
        ancho_logo = 150
        logo = Image(archivo, width=ancho_logo, height=ancho_logo * alto_img / ancho_img)
    else:
        logo = Paragraph(seguro(clinica.nombre), estilos['medico'])

    doctora = atencion.doctor
    datos = [Paragraph(seguro(atencion.doctor_nombre or doctora.get_full_name()).upper(), estilos['medico']),
             Paragraph(seguro(clinica.nombre), estilos['dato'])]
    if getattr(doctora, 'jvpm', ''):
        datos.append(Paragraph('J.V.P.M. ' + seguro(doctora.jvpm), estilos['dato']))
    if clinica.telefono:
        datos.append(Paragraph('Tel. ' + seguro(clinica.telefono), estilos['dato']))
    if clinica.direccion:
        datos.append(Paragraph(seguro(clinica.direccion), estilos['dato']))

    return [Table([[logo, datos]], colWidths=[170, ANCHO_UTIL - 170], style=TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (1, 0), (1, 0), 16),
    ])), Spacer(1, 8), HRFlowable(width='100%', color=GRIS, thickness=0.6), Spacer(1, 10)]


def _seccion(titulo, estilos):
    return Table([[Paragraph(titulo.upper(), estilos['seccion'])]], colWidths=[ANCHO_UTIL], style=TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), FONDO_TITULO),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))


def _texto(titulo, valor, estilos):
    """Una seccion de texto libre; si quedo vacia, lo dice en vez de desaparecer."""
    return [_seccion(titulo, estilos), Spacer(1, 4),
            Paragraph(seguro(valor) if valor else '<i>Sin registrar.</i>', estilos['cuerpo']),
            Spacer(1, 10)]


class FiguraConMarcas(Flowable):
    """
    La figura de la atencion con sus puntos y flechas, dibujados igual que
    en pantalla. x e y vienen en porcentaje de la imagen; en el PDF el eje
    y crece hacia arriba, por eso se invierte.
    """

    def __init__(self, ruta, marcas, ancho):
        super().__init__()
        self.ruta = ruta
        self.marcas = marcas
        ancho_img, alto_img = ImageReader(ruta).getSize()
        self.ancho = ancho
        self.alto = ancho * alto_img / ancho_img

    def wrap(self, *args):
        return self.ancho, self.alto

    def _punto(self, dato):
        return dato['x'] / 100 * self.ancho, self.alto - dato['y'] / 100 * self.alto

    def _flecha(self, canvas, desde, hasta):
        (x1, y1), (x2, y2) = self._punto(desde), self._punto(hasta)
        canvas.line(x1, y1, x2, y2)
        angulo = math.atan2(y2 - y1, x2 - x1)
        largo, abertura = 7, math.radians(25)
        punta = canvas.beginPath()
        punta.moveTo(x2, y2)
        punta.lineTo(x2 - largo * math.cos(angulo - abertura), y2 - largo * math.sin(angulo - abertura))
        punta.lineTo(x2 - largo * math.cos(angulo + abertura), y2 - largo * math.sin(angulo + abertura))
        punta.close()
        canvas.drawPath(punta, stroke=0, fill=1)

    def draw(self):
        canvas = self.canv
        canvas.drawImage(ImageReader(self.ruta), 0, 0, width=self.ancho, height=self.alto)
        canvas.setStrokeColor(GRIS)
        canvas.rect(0, 0, self.ancho, self.alto, stroke=1, fill=0)
        canvas.setStrokeColor(ROJO)
        canvas.setFillColor(ROJO)
        canvas.setLineWidth(1.4)
        for marca in self.marcas:
            for vector in marca.get('vectores', []):
                self._flecha(canvas, marca, vector)
        for numero, marca in enumerate(self.marcas, start=1):
            x, y = self._punto(marca)
            canvas.setStrokeColor(colors.white)
            canvas.setFillColor(ROJO)
            canvas.circle(x, y, 3.6, stroke=1, fill=1)
            canvas.setFont('Helvetica-Bold', 8)
            canvas.drawString(x + 5, y + 3, str(numero))


def _zonas(atencion, estilos):
    """
    La figura y la lista de sus puntos, juntas en una pagina (KeepTogether).
    Sin marcas, la seccion no se imprime: una figura en blanco no dice nada.
    """
    marcas = atencion.marcas or []
    if not marcas:
        return []
    ruta = finders.find(IMAGENES.get(atencion.figura, IMAGENES[AtencionEstetica.Figura.MUJER]))
    filas = []
    for numero, marca in enumerate(marcas, start=1):
        flechas = len(marca.get('vectores', []))
        detalle = seguro(marca.get('nota')) or '<i>Sin nota</i>'
        if flechas:
            detalle += f' · {flechas} {"flecha" if flechas == 1 else "flechas"}'
        filas.append([Paragraph(f'<font color="#c0392b"><b>● {numero}</b></font>', estilos['cuerpo']),
                      Paragraph(detalle, estilos['cuerpo'])])
    lista = Table(filas, colWidths=[34, ANCHO_UTIL - 34], style=TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
    ]))
    return [KeepTogether([_seccion('Zonas a tratar', estilos), Spacer(1, 6),
                          FiguraConMarcas(ruta, marcas, ANCHO_UTIL), Spacer(1, 8), lista]),
            Spacer(1, 10)]


def _signos(atencion, estilos):
    valores = [('P/A', atencion.presion_arterial),
               ('FC', f'{atencion.frecuencia_cardiaca} lpm' if atencion.frecuencia_cardiaca is not None else ''),
               ('TC', f'{atencion.temperatura} °C' if atencion.temperatura is not None else ''),
               ('Saturación', f'{atencion.saturacion} %' if atencion.saturacion is not None else ''),
               ('Peso', f'{atencion.peso} kg' if atencion.peso is not None else ''),
               ('Talla', f'{atencion.talla} m' if atencion.talla is not None else '')]
    celdas = [[Paragraph(etiqueta, estilos['etiqueta']) for etiqueta, _ in valores],
              [Paragraph(seguro(valor) or '—', estilos['cuerpo']) for _, valor in valores]]
    return [_seccion('Signos vitales', estilos), Spacer(1, 4),
            Table(celdas, colWidths=[ANCHO_UTIL / 6] * 6, style=TableStyle([
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 1),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
            ])), Spacer(1, 10)]


def _procedimientos(atencion, estilos):
    """
    La tabla Procedimiento | 1 ... 10 de la paciente, con la fecha de cada
    sesion. Si alguno pasa de 10 sesiones, las siguientes van en otro bloque
    debajo (11 a 20, y asi): diez columnas es lo que cabe en la hoja.
    """
    procedimientos = list(ProcedimientoEstetico.objects.filter(expediente=atencion.expediente_id, activo=True)
                          .prefetch_related('sesiones__atencion'))
    if not procedimientos:
        return []
    sesiones = {p.pk: {s.numero: s for s in p.sesiones.all() if s.activo} for p in procedimientos}
    mas_alta = max((max(fechas, default=0) for fechas in sesiones.values()), default=0)
    por_bloque = ProcedimientoEstetico.COLUMNAS_MINIMAS
    bloques = max(1, math.ceil(mas_alta / por_bloque))
    pequeno = ParagraphStyle('Celda', parent=estilos['cuerpo'], fontSize=7, leading=9, alignment=1)
    ancho_nombre = 150
    partes = [_seccion('Procedimientos', estilos), Spacer(1, 4)]
    for bloque in range(bloques):
        numeros = range(bloque * por_bloque + 1, (bloque + 1) * por_bloque + 1)
        filas = [[Paragraph('<b>Procedimiento</b>', estilos['dato'])]
                 + [Paragraph(f'<b>{n}</b>', pequeno) for n in numeros]]
        for procedimiento in procedimientos:
            propias = sesiones[procedimiento.pk]
            filas.append([Paragraph(seguro(procedimiento.nombre), estilos['dato'])] + [
                Paragraph(timezone.localtime(propias[n].atencion.inicio).strftime('%d/%m') if n in propias else '',
                          pequeno) for n in numeros])
        partes += [Table(filas, colWidths=[ancho_nombre] + [(ANCHO_UTIL - ancho_nombre) / por_bloque] * por_bloque,
                         repeatRows=1, style=TableStyle([
                             ('GRID', (0, 0), (-1, -1), 0.5, GRIS),
                             ('BACKGROUND', (0, 0), (-1, 0), FONDO_TITULO),
                             ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                         ])), Spacer(1, 6)]
    return partes + [Spacer(1, 4)]


def generar_pdf_atencion(atencion):
    persona = atencion.expediente.persona
    estilos = _estilos()
    salida = BytesIO()
    pdf = SimpleDocTemplate(salida, pagesize=letter, leftMargin=54, rightMargin=54,
                            topMargin=40, bottomMargin=45,
                            title=f'Atención estética — {persona}', author=atencion.expediente.clinica.nombre)

    inicio = timezone.localtime(atencion.inicio)
    datos = [
        [Paragraph('Paciente', estilos['etiqueta']), Paragraph('Edad', estilos['etiqueta']),
         Paragraph('DUI', estilos['etiqueta']), Paragraph('Fecha', estilos['etiqueta'])],
        [Paragraph(f'<b>{seguro(persona)}</b>', estilos['cuerpo']),
         Paragraph(f'{persona.edad} años' if persona.edad is not None else '—', estilos['cuerpo']),
         Paragraph(seguro(persona.dui) or '—', estilos['cuerpo']),
         Paragraph(inicio.strftime('%d/%m/%Y %H:%M'), estilos['cuerpo'])],
    ]
    historia = _membrete(atencion, estilos) + [
        Paragraph('Atención estética', estilos['titulo']), Spacer(1, 6),
        Table(datos, colWidths=[ANCHO_UTIL * 0.42, ANCHO_UTIL * 0.14, ANCHO_UTIL * 0.2, ANCHO_UTIL * 0.24],
              style=TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0),
                                ('TOPPADDING', (0, 0), (-1, -1), 1),
                                ('BOTTOMPADDING', (0, 0), (-1, -1), 1)])),
        Spacer(1, 12),
    ]
    historia += _texto('Motivo de la consulta', atencion.motivo, estilos)
    historia += _signos(atencion, estilos)
    historia += _zonas(atencion, estilos)
    historia += _texto('Plan', atencion.plan, estilos)
    historia += _texto('RP', atencion.rp, estilos)
    historia += _procedimientos(atencion, estilos)
    historia += _texto('Descripción del tratamiento', atencion.descripcion_tratamiento, estilos)

    pdf.build(historia)
    return salida.getvalue()


# --- Plantilla en blanco (HU-EST-04) ---

def _renglones(cantidad, alto=24):
    """Lineas para escribir a mano, mas altas que el texto impreso."""
    lineas = []
    for _ in range(cantidad):
        lineas += [Spacer(1, alto - 1), HRFlowable(width='100%', color=GRIS, thickness=0.5)]
    return lineas + [Spacer(1, 10)]


def _campo_en_blanco(etiqueta, estilos):
    return [Paragraph(etiqueta, estilos['etiqueta']), Spacer(1, 16),
            HRFlowable(width='92%', color=GRIS, thickness=0.5, hAlign='LEFT')]


def generar_plantilla_atencion(clinica, profesional, figura):
    """
    La atencion estetica en blanco, para llenarla a mano: mismo formato que
    el PDF de una atencion, con lineas donde va cada dato y la figura sin
    marcas. No crea ningun registro. `figura` es 'mujer' u 'hombre'.
    """
    estilos = _estilos()
    salida = BytesIO()
    pdf = SimpleDocTemplate(salida, pagesize=letter, leftMargin=54, rightMargin=54,
                            topMargin=40, bottomMargin=45, title='Atención estética', author=clinica.nombre)
    # Lo minimo que pide el membrete; no es una atencion de verdad.
    papel = SimpleNamespace(expediente=SimpleNamespace(clinica=clinica), doctor=profesional,
                            doctor_nombre=profesional.get_full_name() or profesional.username)

    datos = Table([[_campo_en_blanco('Paciente', estilos), _campo_en_blanco('Edad', estilos),
                    _campo_en_blanco('DUI', estilos), _campo_en_blanco('Fecha', estilos)]],
                  colWidths=[ANCHO_UTIL * 0.42, ANCHO_UTIL * 0.14, ANCHO_UTIL * 0.2, ANCHO_UTIL * 0.24],
                  style=TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    signos = Table([[_campo_en_blanco(etiqueta, estilos)
                     for etiqueta in ('P/A', 'FC', 'TC', 'Saturación', 'Peso', 'Talla')]],
                   colWidths=[ANCHO_UTIL / 6] * 6,
                   style=TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('VALIGN', (0, 0), (-1, -1), 'TOP')]))

    numeros = range(1, ProcedimientoEstetico.COLUMNAS_MINIMAS + 1)
    pequeno = ParagraphStyle('Celda', parent=estilos['cuerpo'], fontSize=7, leading=9, alignment=1)
    filas = [[Paragraph('<b>Procedimiento</b>', estilos['dato'])] + [Paragraph(f'<b>{n}</b>', pequeno) for n in numeros]]
    filas += [[''] * 11 for _ in range(5)]
    procedimientos = Table(filas, colWidths=[150] + [(ANCHO_UTIL - 150) / 10] * 10,
                           rowHeights=[None] + [22] * 5, style=TableStyle([
                               ('GRID', (0, 0), (-1, -1), 0.5, GRIS),
                               ('BACKGROUND', (0, 0), (-1, 0), FONDO_TITULO),
                               ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                           ]))

    ruta = finders.find(IMAGENES.get(figura, IMAGENES[AtencionEstetica.Figura.MUJER]))
    figura_en_blanco = FiguraConMarcas(ruta, [], ANCHO_UTIL * 0.82)
    figura_en_blanco.hAlign = 'CENTER'
    historia = _membrete(papel, estilos) + [
        Paragraph('Atención estética', estilos['titulo']), Spacer(1, 8), datos, Spacer(1, 14),
        _seccion('Motivo de la consulta', estilos)] + _renglones(2) + [
        _seccion('Signos vitales', estilos), Spacer(1, 6), signos, Spacer(1, 14),
        # La figura y sus renglones, juntos en una pagina, como en el PDF de una atencion.
        # Un poco mas chica que en el PDF de una atencion: asi la figura y sus
        # renglones caben en la primera hoja, junto con los datos.
        KeepTogether([_seccion('Zonas a tratar', estilos), Spacer(1, 6),
                      figura_en_blanco] + _renglones(2, alto=20)),
        # Cada titulo viaja con sus renglones: nunca queda solo al pie de una hoja.
        KeepTogether([_seccion('Plan', estilos)] + _renglones(3)),
        KeepTogether([_seccion('RP', estilos)] + _renglones(4)),
        KeepTogether([_seccion('Procedimientos', estilos), Spacer(1, 4), procedimientos, Spacer(1, 12)]),
        KeepTogether([_seccion('Descripción del tratamiento', estilos)] + _renglones(6))]
    pdf.build(historia)
    return salida.getvalue()
