(function () {
    var DEMORA_MS = 350;
    var MIN_CARACTERES = 2;

    var form = document.getElementById('form-registrar-adulto');
    if (!form) return;

    var urlBuscar = form.dataset.buscarPersonaUrl;

    /* ---- Parentesco "Otro": solo pide el detalle cuando aplica ---- */
    var selectParentesco = document.getElementById('id_contacto_parentesco');
    var filaParentescoOtro = document.getElementById('fila-parentesco-otro');

    function actualizarParentescoOtro() {
        filaParentescoOtro.style.display = selectParentesco.value === 'otro' ? '' : 'none';
    }

    if (selectParentesco) {
        selectParentesco.addEventListener('change', actualizarParentescoOtro);
        actualizarParentescoOtro();
    }

    /* ---- Edad calculada en vivo (HU-EXP-01: "el sistema calcula la edad") ---- */
    var campoFecha = document.getElementById('id_fecha_nacimiento');
    var etiquetaEdad = document.getElementById('edad-calculada');

    function calcularEdad(fechaTexto) {
        if (!fechaTexto) return null;
        var hoy = new Date();
        var nacimiento = new Date(fechaTexto + 'T00:00:00');
        if (isNaN(nacimiento.getTime())) return null;
        var edad = hoy.getFullYear() - nacimiento.getFullYear();
        var mes = hoy.getMonth() - nacimiento.getMonth();
        if (mes < 0 || (mes === 0 && hoy.getDate() < nacimiento.getDate())) edad--;
        return edad;
    }

    function actualizarEdad() {
        var edad = calcularEdad(campoFecha.value);
        etiquetaEdad.textContent = edad === null ? '' : edad + ' años';
    }

    if (campoFecha) {
        campoFecha.addEventListener('change', actualizarEdad);
        actualizarEdad();
    }

    /* ---- Formato automatico: telefono (0000-0000) y DUI (00000000-0) ----
       Se guarda la posicion del cursor porque insertar el guion sin
       ajustarla lo manda al final cada vez que se teclea. */
    function conCursorFijo(campo, formatear) {
        campo.addEventListener('input', function () {
            var largoAntes = campo.value.length;
            var cursorAntes = campo.selectionStart;
            campo.value = formatear(campo.value);
            var diferencia = campo.value.length - largoAntes;
            var nuevaPosicion = Math.max(0, cursorAntes + diferencia);
            campo.setSelectionRange(nuevaPosicion, nuevaPosicion);
        });
    }

    function formatearTelefono(valor) {
        var digitos = valor.replace(/\D/g, '').slice(0, 8);
        return digitos.length > 4 ? digitos.slice(0, 4) + '-' + digitos.slice(4) : digitos;
    }

    function formatearDui(valor) {
        var digitos = valor.replace(/\D/g, '').slice(0, 9);
        return digitos.length > 8 ? digitos.slice(0, 8) + '-' + digitos.slice(8) : digitos;
    }

    ['id_telefono', 'id_contacto_telefono'].forEach(function (id) {
        var campo = document.getElementById(id);
        if (campo) conCursorFijo(campo, formatearTelefono);
    });

    var campoDui = document.getElementById('id_dui');
    if (campoDui) conCursorFijo(campoDui, formatearDui);

    /* ---- Solo letras en nombres y apellidos (nada de numeros ni
       simbolos) -- filtra mientras se escribe, no espera al enviar. */
    function soloLetras(valor) {
        return valor.replace(/[^A-Za-zÁÉÍÓÚáéíóúÑñÜü '\-]/g, '');
    }

    ['id_nombres', 'id_apellidos', 'id_contacto_nombres', 'id_contacto_apellidos'].forEach(function (id) {
        var campo = document.getElementById(id);
        if (!campo) return;
        campo.addEventListener('input', function () {
            var cursor = campo.selectionStart;
            var largoAntes = campo.value.length;
            campo.value = soloLetras(campo.value);
            var diferencia = campo.value.length - largoAntes;
            campo.setSelectionRange(cursor + diferencia, cursor + diferencia);
        });
    });

    /* ---- Buscar y reutilizar un contacto existente ---- */
    var buscador = document.getElementById('buscador-contacto');
    var resultados = document.getElementById('resultados-contacto');
    var bannerVinculado = document.getElementById('contacto-vinculado');
    var nombreVinculado = document.getElementById('contacto-vinculado-nombre');
    var btnDesvincular = document.getElementById('btn-desvincular-contacto');

    var campoId = document.getElementById('id_contacto_persona_id');
    var campoNombres = document.getElementById('id_contacto_nombres');
    var campoApellidos = document.getElementById('id_contacto_apellidos');
    var campoTelefono = document.getElementById('id_contacto_telefono');

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

    if (buscador && urlBuscar) {
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
    }
})();
