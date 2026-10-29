/*
 * Ver el PDF de la atención sin salir de ella -- HU-EST-03.
 *
 * Como en la consulta: el PDF se abre encima, en el visor del navegador,
 * que ya trae imprimir y descargar. Antes se guarda lo pendiente, para que
 * el PDF salga con lo último que escribió la doctora.
 */
(function () {
    'use strict';

    var modal = document.getElementById('modalDocumento');
    var boton = document.querySelector('[data-ver-pdf]');
    if (!modal || !boton) { return; }
    var visor = document.getElementById('modalDocumentoVisor');
    var enlace = document.getElementById('modalDocumentoNuevaPestana');
    var ventana = new bootstrap.Modal(modal);

    boton.addEventListener('click', function () {
        var antes = window.guardarPendiente ? window.guardarPendiente() : Promise.resolve(true);
        antes.then(function (ok) {
            if (!ok) { return; }
            // La hora en la direccion evita que el navegador muestre un PDF viejo.
            var url = boton.dataset.verPdf + '?v=' + Date.now();
            visor.src = url;
            enlace.href = url;
            ventana.show();
        });
    });
    // Al cerrar se descarga el PDF de memoria.
    modal.addEventListener('hidden.bs.modal', function () { visor.src = ''; });
})();
