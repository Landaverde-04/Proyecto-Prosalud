/*
 * Preguardado de la clínica estética: la ficha (HU-EST-01/02) y la atención
 * (HU-EST-03). Sirve para cualquier <form data-preguardado>.
 *
 * Copia del preguardado de la consulta (consultas/js/consulta.js): se guarda
 * en el servidor mientras la doctora escribe, sobre la misma fila, y no en
 * el navegador. Nada recarga la pantalla, así que no se pierde lo escrito
 * ni se mueve de lugar.
 */
(function () {
    'use strict';

    var form = document.querySelector('form[data-preguardado]');
    if (!form || !window.fetch) { return; }

    // Un campo puede estar fuera del <form> y pertenecerle por su atributo
    // form (la descripción del tratamiento va debajo de los procedimientos).
    // Por eso se escucha en todo el documento y se filtra por dueño.
    function esDelFormulario(elemento) {
        var etiqueta = elemento.closest && elemento.closest('label');
        var control = etiqueta && etiqueta.control ? etiqueta.control : elemento;
        return control.form === form;
    }

    var estado = document.getElementById('estado-guardado');
    var url = form.action;
    var token = form.querySelector('[name=csrfmiddlewaretoken]').value;
    var espera = null;
    var peticion = null;
    // Cambios escritos contra cambios confirmados por el servidor.
    var version = 0;
    var versionGuardada = 0;

    function avisar(texto, error) {
        estado.textContent = texto;
        estado.classList.toggle('text-danger', !!error);
        estado.classList.toggle('text-muted', !error);
    }

    function guardar() {
        // Una petición a la vez: si sigue escribiendo mientras se guarda, se
        // encola una sola repetición al terminar.
        if (peticion) {
            return peticion.then(function (ok) {
                return ok && version !== versionGuardada ? guardar() : ok;
            });
        }
        var enviada = version;
        avisar('Guardando…');
        peticion = fetch(url, {
            method: 'POST',
            headers: {'X-CSRFToken': token, 'X-Requested-With': 'XMLHttpRequest'},
            body: new FormData(form),
        })
            .then(function (respuesta) {
                if (respuesta.redirected) { throw new Error('sesion'); }
                // Un 400 trae el motivo en JSON (un correo mal escrito, por
                // ejemplo); un 500 o un 403 traen HTML y caen al catch.
                return respuesta.json().then(function (datos) {
                    if (respuesta.ok) { return datos; }
                    var fallo = new Error('rechazado');
                    fallo.mensaje = datos.mensaje;
                    throw fallo;
                });
            })
            .then(function (datos) {
                versionGuardada = Math.max(versionGuardada, enviada);
                avisar('Guardada a las ' + datos.hora);
                return true;
            })
            .catch(function (error) {
                // Falla visible: en silencio, la doctora creería que quedó
                // guardado y podría cerrar la ventana perdiendo lo escrito.
                avisar(error.mensaje || 'No se pudo guardar. Revise su conexión y no cierre esta ventana.', true);
                return false;
            })
            .finally(function () {
                peticion = null;
            });
        return peticion.then(function (ok) {
            return ok && version !== versionGuardada ? guardar() : ok;
        });
    }

    document.addEventListener('input', function (evento) {
        if (!esDelFormulario(evento.target)) { return; }
        version++;
        clearTimeout(espera);
        avisar('Sin guardar…');
        espera = setTimeout(guardar, 1000);
    });

    // Un Sí/No o un resultado se desmarca tocándolo otra vez: sin marcar
    // significa "sin responder", y el navegador no deja volver a ese estado.
    // Se mira al presionar si ya estaba marcado, porque al soltar el
    // navegador ya lo marcó.
    var presionado = null;
    var estabaMarcado = false;
    document.addEventListener('pointerdown', function (evento) {
        if (!esDelFormulario(evento.target)) { return; }
        var etiqueta = evento.target.closest('label');
        var control = etiqueta && etiqueta.control ? etiqueta.control : evento.target;
        // Elegir la figura no se desmarca: siempre hay una.
        presionado = control.type === 'radio' && !control.hasAttribute('data-no-desmarcar') ? control : null;
        estabaMarcado = !!(presionado && presionado.checked);
    });
    document.addEventListener('click', function (evento) {
        var opcion = evento.target;
        if (opcion.type !== 'radio' || opcion !== presionado || !estabaMarcado) { return; }
        presionado = null;
        opcion.checked = false;
        // Desmarcar por código no avisa al preguardado: se le avisa a mano.
        opcion.dispatchEvent(new Event('input', {bubbles: true}));
    });

    // Al salir de un campo se guarda de una vez, sin esperar el debounce.
    document.addEventListener('focusout', function (evento) {
        if (!esDelFormulario(evento.target)) { return; }
        clearTimeout(espera);
        guardar();
    });

    // Enviar el formulario (el botón "Guardar y volver" de la ficha, o Enter
    // en un campo) nunca recarga: se guarda y, si hay a dónde volver, se va
    // cuando el servidor confirmó. Sin JavaScript se envía como siempre.
    form.addEventListener('submit', function (evento) {
        evento.preventDefault();
        clearTimeout(espera);
        guardar().then(function (ok) {
            if (ok && form.dataset.urlVolver) window.location.href = form.dataset.urlVolver;
        });
    });

    // Finalizar la atención: su ventana manda su propio POST, así que lo
    // escrito se guarda antes de abrirla y otra vez antes de confirmar.
    var abrirFinalizar = document.querySelector('[data-abrir-finalizar]');
    var ventanaFinalizar = document.getElementById('modalFinalizar');
    if (abrirFinalizar && ventanaFinalizar) {
        abrirFinalizar.addEventListener('click', function () {
            clearTimeout(espera);
            guardar().then(function (ok) {
                if (ok) bootstrap.Modal.getOrCreateInstance(ventanaFinalizar).show();
            });
        });
        var formFinalizar = ventanaFinalizar.querySelector('form[data-finalizar]');
        formFinalizar.addEventListener('submit', function (evento) {
            evento.preventDefault();
            clearTimeout(espera);
            guardar().then(function (ok) { if (ok) formFinalizar.submit(); });
        });
    }

    // Salir por "Regresar" tampoco debe perder lo último escrito.
    document.querySelectorAll('[data-salir]').forEach(function (enlace) {
        enlace.addEventListener('click', function (evento) {
            evento.preventDefault();
            clearTimeout(espera);
            guardar().then(function (ok) {
                if (ok) window.location.href = enlace.href;
            });
        });
    });

    // Cualquier otra salida (menú lateral, cerrar la pestaña, recargar): si
    // queda algo sin confirmar se envía con keepalive, que el navegador
    // completa aunque la página ya se esté descargando.
    window.addEventListener('pagehide', function () {
        if (version === versionGuardada) { return; }
        clearTimeout(espera);
        fetch(url, {
            method: 'POST',
            headers: {'X-CSRFToken': token, 'X-Requested-With': 'XMLHttpRequest'},
            body: new FormData(form),
            keepalive: true,
        }).catch(function () { /* la página ya se fue: no hay a quién avisar */ });
    });
})();
