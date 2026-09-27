/*
 * Buscar una Persona existente (por DUI, nombre o telefono) y vincularla
 * a un bloque de formulario, o dejar los campos libres para crear una
 * nueva -- misma logica que HU-EXP-01 ya resolvio, extraida aqui para
 * que HU-EXP-05/06 (agregar contacto adicional desde el expediente) la
 * reutilice sin duplicar el codigo. Antes vivia solo en
 * registrar-paciente.js.
 *
 * `iniciarBuscadorContacto(ids)` recibe los ids de los elementos del
 * bloque (ver registrar-paciente.js y ver-expediente.js para los dos
 * usos reales) -- asi la misma funcion sirve para el formulario de
 * registro y para el modal del expediente, cada uno con sus propios ids
 * en el DOM.
 */
function iniciarBuscadorContacto(ids) {
    var DEMORA_MS = 350;
    var MIN_CARACTERES = 2;

    var buscador = document.getElementById(ids.buscador);
    var urlBuscar = ids.urlBuscar;
    if (!buscador || !urlBuscar) return;

    var resultados = document.getElementById(ids.resultados);
    var bannerVinculado = document.getElementById(ids.bannerVinculado);
    var nombreVinculado = document.getElementById(ids.nombreVinculado);
    var btnDesvincular = document.getElementById(ids.btnDesvincular);

    var campoId = document.getElementById(ids.campoId);
    var campoNombres = document.getElementById(ids.campoNombres);
    var campoApellidos = document.getElementById(ids.campoApellidos);
    var campoTelefono = document.getElementById(ids.campoTelefono);

    var temporizador = null;

    function limpiarResultados() {
        resultados.innerHTML = '';
    }

    function mostrarResultados(lista) {
        if (lista.length === 0) {
            resultados.innerHTML = '<div class="list-group-item text-muted small">Sin coincidencias -- llena los datos abajo para registrarlo.</div>';
            return;
        }
        resultados.innerHTML = lista.map(function (persona) {
            var detalle = [persona.dui, persona.telefono].filter(Boolean).join(' · ');
            return '<button type="button" class="list-group-item list-group-item-action py-2" data-id="' + persona.id + '">' +
                '<div class="fw-medium">' + persona.nombres + ' ' + persona.apellidos + '</div>' +
                (detalle ? '<div class="text-muted small">' + detalle + '</div>' : '') +
                '</button>';
        }).join('');

        Array.from(resultados.querySelectorAll('button')).forEach(function (boton) {
            var persona = lista.find(function (p) { return String(p.id) === boton.dataset.id; });
            boton.addEventListener('click', function () {
                vincularContacto(persona);
            });
        });
    }

    function vincularContacto(persona) {
        campoId.value = persona.id;
        campoNombres.value = persona.nombres;
        campoApellidos.value = persona.apellidos;
        campoTelefono.value = persona.telefono || '';

        [campoNombres, campoApellidos, campoTelefono].forEach(function (campo) {
            campo.readOnly = true;
        });

        nombreVinculado.textContent = persona.nombres + ' ' + persona.apellidos;
        bannerVinculado.classList.remove('d-none');
        buscador.value = '';
        limpiarResultados();
        buscador.classList.add('d-none');
    }

    function desvincularContacto() {
        campoId.value = '';
        campoNombres.value = '';
        campoApellidos.value = '';
        campoTelefono.value = '';

        [campoNombres, campoApellidos, campoTelefono].forEach(function (campo) {
            campo.readOnly = false;
        });

        bannerVinculado.classList.add('d-none');
        buscador.classList.remove('d-none');
        buscador.focus();
    }

    if (btnDesvincular) {
        btnDesvincular.addEventListener('click', desvincularContacto);
    }

    buscador.addEventListener('input', function () {
        clearTimeout(temporizador);
        var texto = buscador.value.trim();
        if (texto.length < MIN_CARACTERES) {
            limpiarResultados();
            return;
        }
        temporizador = setTimeout(function () {
            fetch(urlBuscar + '?q=' + encodeURIComponent(texto), {
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
            })
                .then(function (resp) { return resp.json(); })
                .then(function (datos) { mostrarResultados(datos.resultados); })
                .catch(limpiarResultados);
        }, DEMORA_MS);
    });

    // Devuelto por si quien lo usa necesita resetear el widget a mano
    // (ej. al cerrar el modal de "agregar contacto" sin guardar).
    return { desvincular: desvincularContacto };
}
