/*
 * Listados sin recarga de página: buscar, filtrar y paginar actualizan
 * solo el contenedor de resultados via fetch().
 *
 * Marcado esperado en la plantilla:
 *   <div data-listado>
 *     <form method="get">...</form>          <-- un solo form dentro
 *     <div data-listado-resultados>
 *       {% include "..._resultados....html" %}
 *     </div>
 *   </div>
 *
 * Enlaces dentro de data-listado-resultados que deben interceptarse
 * (paginacion, "limpiar", "ver todos") necesitan el atributo
 * data-listado-link. Los demas (editar, detalle, etc.) navegan normal.
 *
 * La vista debe devolver solo el fragmento de resultados cuando detecta
 * el header X-Requested-With: XMLHttpRequest, y la pagina completa en
 * cualquier otro caso -- asi funciona igual con o sin JavaScript.
 */
(function () {
    var DEMORA_MS = 350;
    var MIN_CARACTERES = 2;

    document.querySelectorAll('[data-listado]').forEach(function (contenedor) {
        var form = contenedor.querySelector('form');
        var resultados = contenedor.querySelector('[data-listado-resultados]');
        if (!form || !resultados) return;

        var temporizador = null;

        function marcarCargando(activo) {
            resultados.style.opacity = activo ? '.5' : '';
            resultados.style.pointerEvents = activo ? 'none' : '';
        }

        function cargar(url, empujarHistorial) {
            marcarCargando(true);
            fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
                .then(function (resp) {
                    if (!resp.ok) throw new Error('respuesta no valida');
                    return resp.text();
                })
                .then(function (html) {
                    resultados.innerHTML = html;
                    if (empujarHistorial !== false) {
                        window.history.pushState({ listadoUrl: url }, '', url);
                    }
                })
                .catch(function () {
                    // Si algo falla (red, permisos cambiados a medio camino),
                    // se cae a una recarga normal en vez de dejar la UI colgada.
                    window.location.href = url;
                })
                .finally(function () {
                    marcarCargando(false);
                });
        }

        function urlDesdeFormulario(reiniciarPagina) {
            var datos = new FormData(form);
            var params = new URLSearchParams();
            datos.forEach(function (valor, clave) {
                if (valor) params.append(clave, valor);
            });
            if (!reiniciarPagina) {
                var pagina = new URLSearchParams(window.location.search).get('page');
                if (pagina) params.set('page', pagina);
            }
            var query = params.toString();
            return form.action.split('?')[0] + (query ? '?' + query : '');
        }

        function onFiltroCambiado() {
            cargar(urlDesdeFormulario(true));
        }

        form.addEventListener('submit', function (evento) {
            evento.preventDefault();
            clearTimeout(temporizador);
            onFiltroCambiado();
        });

        form.querySelectorAll('input[type="text"], input[type="search"]').forEach(function (campo) {
            campo.addEventListener('input', function () {
                clearTimeout(temporizador);
                var valor = campo.value.trim();
                if (valor.length > 0 && valor.length < MIN_CARACTERES) return;
                temporizador = setTimeout(onFiltroCambiado, DEMORA_MS);
            });
        });

        form.querySelectorAll('input[type="date"], select').forEach(function (campo) {
            campo.addEventListener('change', function () {
                clearTimeout(temporizador);
                onFiltroCambiado();
            });
        });

        contenedor.addEventListener('click', function (evento) {
            var enlace = evento.target.closest('a[data-listado-link]');
            if (!enlace) return;
            evento.preventDefault();
            clearTimeout(temporizador);
            cargar(enlace.getAttribute('href'));
        });

        window.addEventListener('popstate', function () {
            cargar(window.location.href, false);
        });
    });
})();
