"""
Separar los mensajes de Django segun si interrumpen o no.

Antes todos salian igual: como aviso en la pagina Y como modal que se abre
solo. Guardar cualquier cosa abria una ventana que habia que cerrar a mano,
y durante una consulta eso pasa varias veces seguidas.

El corte esta en `WARNING` (30), que es el nivel a partir del cual Django
considera que algo salio mal:

    DEBUG 10 · INFO 20 · SUCCESS 25  ->  pasajero, se cierra solo
    WARNING 30 · ERROR 40            ->  bloqueante, se confirma a mano
"""

from django import template
from django.contrib import messages

register = template.Library()


@register.filter
def bloqueantes(lista):
    """Advertencias y errores: se leen y se confirman."""
    return [m for m in lista if m.level >= messages.WARNING]


@register.filter
def pasajeros(lista):
    """Exito e informacion: se muestran y se van solos."""
    return [m for m in lista if m.level < messages.WARNING]
