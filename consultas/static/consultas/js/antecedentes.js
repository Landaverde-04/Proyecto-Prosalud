/*
 * Corregir un antecedente sin salir de la lista -- HU-EXP-26 del criterio
 * "registrar y editar" (completado el 21/09/2026).
 *
 * El formulario de cada fila ya viene dibujado y escondido desde el
 * servidor: el lapiz solo lo muestra. Sin JavaScript la pagina sigue
 * funcionando, solo que los formularios se ven todos abiertos a la vez --
 * feos, pero utiles.
 */
(function () {
    'use strict';

    var lista = document.querySelector('[data-antecedente]');
    if (!lista) { return; }

    // Delegado en el documento: asi da igual cuantas filas haya.
    document.addEventListener('click', function (evento) {
        var fila = evento.target.closest('[data-antecedente]');
        if (!fila) { return; }
        if (evento.target.closest('[data-editar-antecedente]')) {
            mostrarEdicion(fila, true);
        } else if (evento.target.closest('[data-cancelar-edicion]')) {
            mostrarEdicion(fila, false);
        }
    });

    function mostrarEdicion(fila, editando) {
        fila.querySelectorAll('[data-modo]').forEach(function (parte) {
            parte.hidden = (parte.dataset.modo === 'editar') !== editando;
        });
        if (editando) { fila.querySelector('select, textarea').focus(); }
    }
})();
