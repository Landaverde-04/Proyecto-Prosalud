"""
Paginación y listados sin recarga, estándar para todo el sistema.

Un solo número en un solo lugar: todas las vistas se comportan igual, y
cambiar el tamaño de página no implica tocar cada una por separado.
"""

from django.core.paginator import Paginator

FILAS_POR_PAGINA = 10


def paginar(queryset, request):
    paginador = Paginator(queryset, FILAS_POR_PAGINA)
    return paginador.get_page(request.GET.get('page'))


def es_ajax(request):
    """
    ¿La pidió listado-vivo.js (core/static/core/js/listado-vivo.js)?

    Si es así, la vista debe devolver solo el fragmento de resultados, no
    la página completa con sidebar y formulario. Sin JavaScript, este
    header nunca llega y todo sigue funcionando como una página normal.
    """
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'
