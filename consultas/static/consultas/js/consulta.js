/*
 * Preguardado de la consulta en atención -- HU-EXP-17.
 *
 * La doctora escribe durante la atención y no debe perder nada si cierra
 * la ventana por error. Se guarda en el servidor, sobre la misma fila de
 * la consulta, no en el navegador: si guardáramos en localStorage, el
 * texto se perdería al cambiar de computadora o al limpiar el navegador,
 * y son datos clínicos.
 *
 * Mismo criterio de debounce que el resto del sistema (listado-vivo.js):
 * no una petición por tecla.
 */
(function () {
    'use strict';

    var form = document.getElementById('form-consulta');
    if (!form) { return; }

    var estado = document.getElementById('estado-borrador');
    var url = form.dataset.urlBorrador;
    var token = form.querySelector('[name=csrfmiddlewaretoken]').value;
    var espera = null;
    var guardando = false;
    var pendiente = false;

    function avisar(texto, error) {
        estado.textContent = texto;
        estado.classList.toggle('text-danger', !!error);
        estado.classList.toggle('text-muted', !error);
    }

    function guardar() {
        // Una petición a la vez: si el usuario sigue escribiendo mientras
        // se guarda, se encola una sola repetición al terminar.
        if (guardando) { pendiente = true; return Promise.resolve(); }
        guardando = true;
        avisar('Guardando…');
        return fetch(url, {
            method: 'POST',
            headers: {'X-CSRFToken': token, 'X-Requested-With': 'XMLHttpRequest'},
            body: new FormData(form),
        })
            .then(function (respuesta) {
                if (!respuesta.ok) { throw new Error(respuesta.status); }
                return respuesta.json();
            })
            .then(function (datos) {
                avisar('Guardado ' + datos.hora);
            })
            .catch(function () {
                // Falla visible: en silencio, la doctora creería que quedó
                // guardado y podría cerrar la ventana perdiendo lo escrito.
                avisar('No se pudo guardar. Revise su conexión y no cierre esta ventana.', true);
            })
            .finally(function () {
                guardando = false;
                if (pendiente) { pendiente = false; guardar(); }
            });
    }

    form.addEventListener('input', function () {
        clearTimeout(espera);
        avisar('Sin guardar…');
        espera = setTimeout(guardar, 1000);
    });

    // Al salir de un campo se guarda de una vez, sin esperar el debounce.
    form.addEventListener('focusout', function () {
        clearTimeout(espera);
        guardar();
    });

    // Antes de abrir la ventana de finalizar: esa ventana manda su propio
    // POST y no arrastra el formulario, así que lo escrito debe estar
    // guardado. Se guarda primero y la ventana se abre después.
    var finalizar = document.querySelector('[data-abrir-finalizar]');
    if (finalizar) {
        finalizar.addEventListener('click', function () {
            clearTimeout(espera);
            guardar().finally(function () {
                new bootstrap.Modal(document.getElementById('modalFinalizar')).show();
            });
        });
    }

    // "Agregar documento (opcional)" del mockup: el botón despliega sus
    // campos aquí mismo, sin salir de la consulta.
    document.querySelectorAll('[data-panel]').forEach(function (boton) {
        boton.addEventListener('click', function () {
            var panel = document.getElementById(boton.dataset.panel);
            panel.hidden = !panel.hidden;
            boton.classList.toggle('active', !panel.hidden);
            if (!panel.hidden) {
                // Lo escrito en la consulta se guarda antes: enviar este
                // formulario recarga la página.
                clearTimeout(espera);
                guardar();
                panel.querySelector('input, select, textarea').focus();
            }
        });
    });

    // Salir a otra pantalla no debe perder lo último escrito: se guarda
    // primero y se navega cuando el servidor confirmó.
    document.querySelectorAll('[data-salir]').forEach(function (enlace) {
        enlace.addEventListener('click', function (evento) {
            evento.preventDefault();
            clearTimeout(espera);
            guardar().finally(function () {
                window.location.href = enlace.href;
            });
        });
    });
})();

/*
 * Dos correcciones pedidas por Samuel el 08/09/2026, ambas sobre lo mismo:
 * atender una consulta no debe interrumpirse.
 */
(function () {
    'use strict';

    /* 1. Revisar un documento sin salir de la consulta.
     *
     * Antes cada "Ver PDF" navegaba a otra pantalla, y volver a la atención
     * costaba tres pasos (expediente → historial → continuar) con el
     * paciente enfrente. Ahora el documento se abre encima.
     */
    var modal = document.getElementById('modalDocumento');
    if (modal) {
        var visor = document.getElementById('modalDocumentoVisor');
        var titulo = document.getElementById('modalDocumentoTitulo');
        var enlace = document.getElementById('modalDocumentoNuevaPestana');
        var ventana = new bootstrap.Modal(modal);
        document.querySelectorAll('[data-ver-pdf]').forEach(function (boton) {
            boton.addEventListener('click', function () {
                visor.src = boton.dataset.verPdf;
                enlace.href = boton.dataset.verPdf;
                titulo.textContent = boton.dataset.titulo || 'Documento';
                ventana.show();
            });
        });
        // Al cerrar se descarga el PDF de memoria: si no, sigue ahí cargado
        // y el siguiente documento aparece un instante con el anterior.
        modal.addEventListener('hidden.bs.modal', function () { visor.src = ''; });
    }

    /* 1b. Ver una aplicación o un control sin salir de la consulta.
     *
     * El contenido ya está en la página, oculto; la ventana solo lo copia y
     * lo muestra. Así no hace falta ir a otra pantalla para leer una dosis.
     */
    var detalle = document.getElementById('modalDetalle');
    if (detalle) {
        var cuerpo = document.getElementById('modalDetalleCuerpo');
        var tituloDetalle = document.getElementById('modalDetalleTitulo');
        var ventanaDetalle = new bootstrap.Modal(detalle);
        document.querySelectorAll('[data-ver-detalle]').forEach(function (boton) {
            boton.addEventListener('click', function () {
                var origen = document.getElementById(boton.dataset.verDetalle);
                if (!origen) { return; }
                cuerpo.innerHTML = origen.innerHTML;
                tituloDetalle.textContent = boton.dataset.titulo || 'Detalle';
                ventanaDetalle.show();
            });
        });
    }

    /* 2. Volver al mismo punto después de guardar.
     *
     * Agregar un documento es un POST que recarga la pantalla, y el
     * navegador la deja arriba del todo. Con la consulta llena de campos,
     * eso obliga a buscar otra vez dónde se iba.
     */
    var CLAVE = 'consulta-scroll:' + window.location.pathname;
    // sessionStorage puede fallar (ventana privada, cookies bloqueadas). Si
    // falla, la pantalla simplemente vuelve arriba como antes.
    function recordar(valor) {
        try { sessionStorage.setItem(CLAVE, valor); } catch (e) { /* sin guardar */ }
    }
    function recordado() {
        try { return sessionStorage.getItem(CLAVE); } catch (e) { return null; }
    }
    document.querySelectorAll('form[action]').forEach(function (formulario) {
        formulario.addEventListener('submit', function () {
            recordar(String(window.scrollY));
        });
    });
    var guardado = recordado();
    if (guardado !== null) {
        try { sessionStorage.removeItem(CLAVE); } catch (e) { /* nada */ }
        // Después del pintado, si no el navegador lo sobrescribe.
        window.requestAnimationFrame(function () {
            window.scrollTo(0, parseInt(guardado, 10) || 0);
        });
    }
})();
