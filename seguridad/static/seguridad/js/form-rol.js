/*
 * Permisos del rol agrupados por modulo: cada grupo se despliega por
 * separado y tiene una casilla para marcar o desmarcar todo el grupo.
 * Sin JavaScript la lista se ve completa y abierta, igual funciona.
 */
(function () {
    'use strict';

    document.querySelectorAll('[data-grupo-permisos]').forEach(function (grupo) {
        var boton = grupo.querySelector('[data-grupo-toggle]');
        var cuerpo = grupo.querySelector('[data-grupo-cuerpo]');
        var todos = grupo.querySelector('[data-grupo-todos]');
        var contador = grupo.querySelector('[data-grupo-contador]');
        var casillas = cuerpo.querySelectorAll('input[type="checkbox"]');

        function actualizar() {
            var marcadas = cuerpo.querySelectorAll('input[type="checkbox"]:checked').length;
            contador.textContent = marcadas + ' de ' + casillas.length;
            todos.checked = marcadas === casillas.length;
            // Estado intermedio: el grupo tiene algunos permisos, no todos.
            todos.indeterminate = marcadas > 0 && marcadas < casillas.length;
        }

        function abrir(abierto) {
            cuerpo.hidden = !abierto;
            boton.setAttribute('aria-expanded', abierto ? 'true' : 'false');
        }

        boton.addEventListener('click', function () {
            abrir(cuerpo.hidden);
        });

        todos.addEventListener('change', function () {
            casillas.forEach(function (casilla) { casilla.checked = todos.checked; });
            actualizar();
        });

        cuerpo.addEventListener('change', actualizar);

        // Cerrados al entrar: el contador ya dice cuanto tiene cada grupo.
        abrir(false);
        actualizar();
    });
})();
