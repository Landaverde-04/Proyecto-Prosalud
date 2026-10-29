"""
Mayuscula inicial automatica en nombres de personas, en todo el sistema
(pedido de Samuel, 29/10/2026): pacientes y contactos (pacientes.Persona),
usuarios (seguridad.Usuario) y los nombres de la ficha estetica.

Vive en core porque la usan modulos que no dependen entre si.
"""


# Palabras de union de los apellidos que van en minuscula ("Lopez de
# Garcia", "de la Cruz"), salvo al inicio.
UNIONES_DE_NOMBRE = {'de', 'del', 'la', 'las', 'los'}


def _mayuscula_inicial(parte):
    # Escrita toda en minuscula o toda en mayuscula ("rosa", "ROSA"): se
    # arregla entera. Mezclada a proposito ("McDonald"): solo la inicial.
    if parte.islower() or parte.isupper():
        return parte[:1].upper() + parte[1:].lower()
    return parte[:1].upper() + parte[1:]


def formatear_nombre(texto):
    """
    Mayuscula inicial en cada palabra de un nombre o apellido: "rosa MARIA"
    -> "Rosa Maria". Las uniones ("de", "del", "la"...) quedan en minuscula,
    como en "Lopez de Garcia" de una paciente casada (pedido de Samuel,
    29/10/2026). Los compuestos con guion tambien: "perez-gomez" ->
    "Perez-Gomez".
    """
    palabras = []
    for posicion, palabra in enumerate((texto or '').split()):
        if posicion > 0 and palabra.lower() in UNIONES_DE_NOMBRE:
            palabras.append(palabra.lower())
        else:
            palabras.append('-'.join(_mayuscula_inicial(parte) for parte in palabra.split('-')))
    return ' '.join(palabras)
