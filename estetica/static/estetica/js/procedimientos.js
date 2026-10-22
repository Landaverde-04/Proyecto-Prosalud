/*
 * Procedimientos de la atención estética, sin recargar la pantalla -- HU-EST-03.
 *
 * Como la receta de la consulta: el servidor devuelve la tabla ya dibujada y
 * se cambia en su sitio, así la página no se mueve. Sin JavaScript, los
 * formularios se envían como siempre y la vista vuelve a la atención.
 */
(function () {
    'use strict';

    var contenedor = document.getElementById('procedimientos');
    if (!contenedor || !window.fetch) { return; }

    function avisarSiSePuede(texto, tipo) {
        if (window.avisar && texto) { window.avisar(texto, tipo); }
    }

    // Delegado: la tabla se redibuja entera en cada cambio, así que un
    // listener por botón se perdería en el primer redibujado.
    contenedor.addEventListener('submit', function (evento) {
        var formulario = evento.target;
        if (!formulario.matches('[data-procedimiento]')) { return; }
        evento.preventDefault();
        var boton = formulario.querySelector('button');
        // Un doble clic no manda dos veces lo mismo.
        if (boton.disabled) { return; }
        boton.disabled = true;
        var agregando = !!formulario.querySelector('input[name=nombre]');

        fetch(formulario.action, {
            method: 'POST',
            headers: {'X-Requested-With': 'XMLHttpRequest'},
            body: new FormData(formulario),
        }).then(function (respuesta) {
            // Un 403 o un 500 traen HTML, no JSON: sin esto el clic se
            // quedaría sin respuesta.
            return respuesta.json().catch(function () { throw new Error(respuesta.status); });
        }).then(function (datos) {
            contenedor.innerHTML = datos.html;
            avisarSiSePuede(datos.mensaje, datos.tipo);
            // Listo para el siguiente procedimiento, sin buscar el campo.
            if (agregando && datos.ok) {
                var campo = contenedor.querySelector('input[name=nombre]');
                if (campo) { campo.focus(); }
            }
        }).catch(function () {
            // NO se reenvía: si el servidor alcanzó a guardar y lo que se
            // perdió fue la respuesta, reenviar marcaría la sesión dos veces.
            boton.disabled = false;
            avisarSiSePuede('No se pudo confirmar el cambio. Recargue la página para revisar los procedimientos.',
                            'danger');
        });
    });
})();
