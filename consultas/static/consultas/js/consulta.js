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

    // Antes de abrir el modal de finalizar: el modal manda su propio POST
    // y no arrastra el formulario, así que lo escrito debe estar guardado.
    var finalizar = document.querySelector('[data-confirmar]');
    if (finalizar) {
        finalizar.addEventListener('click', function () {
            clearTimeout(espera);
            guardar();
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
