/* Correcciones durante la atencion: no reemplaza los campos clinicos. */
(function () {
    'use strict';
    var boton = document.querySelector('[data-editar-preconsulta]');
    if (!boton) return;
    var bloque = boton.closest('[data-signos-vivos]');
    var editor = document.getElementById('editor-preconsulta');
    var form = document.getElementById('form-preconsulta-consulta');
    var campos = form.querySelector('[data-preconsulta-campos]');
    var estado = form.querySelector('[data-preconsulta-estado]');
    var version = form.elements.version_preconsulta;
    var cambios = false;
    var peticion = null;
    var cargando = false;
    var cierre = document.querySelector('#modalFinalizar form');

    function actualizarCierre() {
        if (!cierre) return;
        cierre.elements.preconsulta_pendiente.value = cambios || peticion || cargando ? '1' : '0';
        cierre.querySelectorAll('[data-preconsulta-cierre]').forEach(function (input) { input.remove(); });
        // El servidor comprueba tambien que este contenido ya esta guardado.
        if (version.value && campos.querySelector('input')) {
            var valores = new FormData(form);
            valores.forEach(function (valor, nombre) {
                if (nombre === 'csrfmiddlewaretoken') return;
                var input = document.createElement('input');
                input.type = 'hidden';
                input.name = nombre === 'version_preconsulta' ? 'preconsulta_version' : 'preconsulta_' + nombre;
                input.value = valor;
                input.setAttribute('data-preconsulta-cierre', '');
                cierre.appendChild(input);
            });
        }
    }

    function avisar(texto, error) {
        estado.textContent = texto;
        estado.classList.toggle('text-danger', !!error);
        estado.classList.toggle('text-muted', !error);
    }
    function cerrar() {
        editor.hidden = true;
        boton.disabled = false;
        boton.setAttribute('aria-expanded', 'false');
        bloque.dataset.editandoPreconsulta = 'false';
        cambios = false;
        actualizarCierre();
    }
    function prepararCampos() {
        var peso = form.elements.peso;
        var talla = form.elements.talla;
        var presion = form.elements.presion_arterial;
        function imc() {
            var salida = form.querySelector('#imc-calculado');
            if (!salida || !talla) return;
            var p = parseFloat(peso.value), t = parseFloat(talla.value);
            salida.textContent = p > 0 && t > 0 ? (p / (t * t)).toFixed(1) : '—';
        }
        if (talla) {
            conCursorFijo(talla, function (valor) {
                var d = valor.replace(/\D/g, '').slice(0, 3);
                return d.length > 1 ? d.slice(0, 1) + '.' + d.slice(1) : d;
            });
            talla.addEventListener('input', imc);
        }
        if (presion) conCursorFijo(presion, function (valor) {
            var d = valor.replace(/\D/g, '').slice(0, 5);
            return d.length > 3 ? d.slice(0, 3) + '/' + d.slice(3) : d;
        });
        peso.addEventListener('input', imc);
        imc();
    }
    boton.addEventListener('click', function () {
        cargando = true;
        actualizarCierre();
        boton.disabled = true;
        bloque.dataset.editandoPreconsulta = 'true';
        editor.hidden = false;
        campos.innerHTML = '';
        avisar('Cargando preconsulta…');
        fetch(form.action, {headers: {'X-Requested-With': 'XMLHttpRequest'}})
            .then(function (resp) {
                if (!resp.ok || resp.redirected) throw new Error('No se pudo abrir la preconsulta. Recargue para comprobar si la consulta sigue abierta.');
                return resp.json();
            }).then(function (datos) {
                campos.innerHTML = datos.campos;
                version.value = datos.version;
                prepararCampos();
                boton.setAttribute('aria-expanded', 'true');
                avisar('');
                campos.querySelector('input').focus();
            }).catch(function (error) { avisar(error.message, true); })
            .finally(function () { cargando = false; actualizarCierre(); });
    });
    form.addEventListener('input', function () {
        cambios = true;
        avisar('Cambios sin guardar.');
        actualizarCierre();
    });
    function guardar() {
        if (cargando) return Promise.resolve(false);
        if (peticion) return peticion;
        if (!cambios) { cerrar(); return Promise.resolve(true); }
        if (!form.reportValidity()) return Promise.resolve(false);
        avisar('Guardando preconsulta…');
        // Evita que se siga editando un valor distinto al que se envio.
        var datos = new FormData(form);
        campos.disabled = true;
        form.querySelectorAll('button').forEach(function (b) { b.disabled = true; });
        peticion = fetch(form.action, {
            method: 'POST', headers: {'X-Requested-With': 'XMLHttpRequest'}, body: datos,
        }).then(function (resp) {
            if (resp.redirected) throw new Error('La sesión venció. No se guardaron los cambios.');
            if (!(resp.headers.get('Content-Type') || '').includes('application/json')) {
                throw new Error('No se pudo guardar la preconsulta. Revise su conexión y permisos.');
            }
            return resp.json().then(function (datos) {
                if (!resp.ok || !datos.ok) {
                    var errores = datos.errores ? Object.values(datos.errores).flat().join(' ') : '';
                    throw new Error(datos.mensaje + (errores ? ' ' + errores : ''));
                }
                return datos;
            });
        }).then(function (datos) {
            bloque.querySelector('[data-signos-contenido]').innerHTML = datos.signos;
            version.value = datos.version;
            avisar(datos.mensaje);
            cerrar();
            if (window.avisar) window.avisar(datos.mensaje, 'success');
            return true;
        }).catch(function (error) {
            avisar(error instanceof TypeError ? 'No se pudo guardar la preconsulta. Revise su conexión.' : error.message, true);
            return false;
        }).finally(function () {
            campos.disabled = false;
            form.querySelectorAll('button').forEach(function (b) { b.disabled = false; });
            peticion = null;
            actualizarCierre();
        });
        return peticion;
    }
    form.addEventListener('submit', function (evento) { evento.preventDefault(); guardar(); });
    form.querySelector('[data-cancelar-preconsulta]').addEventListener('click', function () {
        if (cargando || peticion) return;
        if (cambios && !window.confirm('¿Descartar los cambios de la preconsulta que aún no guardó?')) return;
        version.value = '';
        campos.innerHTML = '';
        cerrar();
    });
    // Regresar y Finalizar deben confirmar tambien las correcciones pendientes.
    window.guardarPreconsultaPendiente = function () {
        return editor.hidden ? Promise.resolve(true) : guardar();
    };
    window.validarPreconsultaGuardada = function () {
        actualizarCierre();
        if (cambios || peticion || cargando) {
            avisar('Guarde los cambios de la preconsulta antes de finalizar la consulta.', true);
            editor.hidden = false;
            estado.scrollIntoView({behavior: 'smooth', block: 'center'});
            return false;
        }
        return true;
    };
    window.addEventListener('beforeunload', function (evento) {
        if (cambios) { evento.preventDefault(); evento.returnValue = ''; }
    });
})();
