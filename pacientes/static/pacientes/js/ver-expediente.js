/* Todo en un solo IIFE exterior (funciones compartidas + las dos
   secciones de modal) para no dejar nada en el scope global, mismo
   criterio que el resto de los .js del proyecto. */
(function () {

/* ---- Utilidades compartidas por los modales de Agregar y Editar contacto ---- */

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

function soloLetras(valor) {
    return valor.replace(/[^A-Za-zÁÉÍÓÚáéíóúÑñÜü '\-]/g, '');
}

function filtrarSoloLetras(id) {
    var campo = document.getElementById(id);
    if (!campo) return;
    campo.addEventListener('input', function () {
        var cursor = campo.selectionStart;
        var largoAntes = campo.value.length;
        campo.value = soloLetras(campo.value);
        var diferencia = campo.value.length - largoAntes;
        campo.setSelectionRange(cursor + diferencia, cursor + diferencia);
    });
}

/* ---- Modal "Agregar contacto" (HU-EXP-05/06) ---- */
(function () {
    var form = document.getElementById('form-agregar-contacto');
    if (!form) return;

    if (typeof iniciarBuscadorContacto === 'function') {
        iniciarBuscadorContacto({
            urlBuscar: form.dataset.buscarPersonaUrl,
            buscador: 'buscador-contacto-modal',
            resultados: 'resultados-contacto-modal',
            bannerVinculado: 'contacto-vinculado-modal',
            nombreVinculado: 'contacto-vinculado-modal-nombre',
            btnDesvincular: 'btn-desvincular-contacto-modal',
            campoId: 'id_persona_id',
            campoNombres: 'id_nombres',
            campoApellidos: 'id_apellidos',
            campoTelefono: 'id_telefono',
        });
    }

    var selectParentesco = document.getElementById('id_parentesco');
    var filaParentescoOtro = document.getElementById('fila-parentesco-otro-modal');
    function actualizarParentescoOtro() {
        filaParentescoOtro.style.display = selectParentesco.value === 'otro' ? '' : 'none';
    }
    if (selectParentesco) {
        selectParentesco.addEventListener('change', actualizarParentescoOtro);
        actualizarParentescoOtro();
    }

    var campoTelefono = document.getElementById('id_telefono');
    if (campoTelefono) conCursorFijo(campoTelefono, formatearTelefono);

    filtrarSoloLetras('id_nombres');
    filtrarSoloLetras('id_apellidos');

    // Reabrir el modal si el servidor devolvio errores (ver
    // 'abrir_modal_contacto' en views.py) -- sin esto, un envio fallido
    // deja los errores escondidos detras de un modal ya cerrado.
    if (form.dataset.abrirModal === 'true') {
        var Modal = window.bootstrap && window.bootstrap.Modal;
        var elemento = document.getElementById('modalAgregarContacto');
        if (Modal && elemento) Modal.getOrCreateInstance(elemento).show();
    }
})();

/* ---- Modal "Editar contacto" (actualizacion HU-EXP-05, 05/09/2026) ----
   Un solo modal compartido por todos los contactos de la lista: cada
   boton "Editar" llena sus campos via data-* al hacer clic. Si el
   nombre o telefono cambian respecto a lo que ya tenia la Persona, se
   pide una confirmacion extra antes de enviar -- esa Persona puede
   estar vinculada a otros pacientes, o ser paciente ella misma. */
(function () {
    var formEditar = document.getElementById('form-editar-contacto');
    if (!formEditar) return;

    var Modal = window.bootstrap && window.bootstrap.Modal;
    var modalEditarEl = document.getElementById('modalEditarContacto');
    var modalConfirmarPersonaEl = document.getElementById('modalConfirmarCambioPersona');

    var campoTipo = document.getElementById('id_editar_tipo');
    var campoNombres = document.getElementById('id_editar_nombres');
    var campoApellidos = document.getElementById('id_editar_apellidos');
    var campoTelefono = document.getElementById('id_editar_telefono');
    var campoParentesco = document.getElementById('id_editar_parentesco');
    var campoParentescoOtro = document.getElementById('id_editar_parentesco_otro');
    var filaParentescoOtro = document.getElementById('fila-parentesco-otro-editar');

    function actualizarParentescoOtroEditar() {
        filaParentescoOtro.style.display = campoParentesco.value === 'otro' ? '' : 'none';
    }
    if (campoParentesco) {
        campoParentesco.addEventListener('change', actualizarParentescoOtroEditar);
        actualizarParentescoOtroEditar();
    }

    if (campoTelefono) conCursorFijo(campoTelefono, formatearTelefono);
    filtrarSoloLetras('id_editar_nombres');
    filtrarSoloLetras('id_editar_apellidos');

    // Valores originales de la Persona contra los que se compara al
    // enviar -- se actualizan cada vez que se abre el modal para un
    // contacto (por clic, o al reabrirlo tras un error de validacion).
    var original = { nombres: '', apellidos: '', telefono: '' };

    function llenarDesdeBoton(boton) {
        if (campoTipo.tagName === 'SELECT') campoTipo.value = boton.dataset.tipo;
        campoNombres.value = boton.dataset.nombres;
        campoApellidos.value = boton.dataset.apellidos;
        campoTelefono.value = boton.dataset.telefono;
        campoParentesco.value = boton.dataset.parentesco;
        campoParentescoOtro.value = boton.dataset.parentescoOtro;
        actualizarParentescoOtroEditar();

        original.nombres = boton.dataset.nombres;
        original.apellidos = boton.dataset.apellidos;
        original.telefono = boton.dataset.telefono;
    }

    document.querySelectorAll('[data-editar-contacto]').forEach(function (boton) {
        boton.addEventListener('click', function () {
            formEditar.action = boton.dataset.url;
            llenarDesdeBoton(boton);
            if (Modal && modalEditarEl) Modal.getOrCreateInstance(modalEditarEl).show();
        });
    });

    function cambioNombreOTelefono() {
        return (
            campoNombres.value.trim() !== original.nombres
            || campoApellidos.value.trim() !== original.apellidos
            || campoTelefono.value.trim() !== original.telefono
        );
    }

    formEditar.addEventListener('submit', function (event) {
        // Ya se confirmo el cambio en el modal de advertencia -- dejar
        // pasar este segundo intento sin volver a interceptarlo.
        if (formEditar.dataset.confirmado === 'true') return;

        if (cambioNombreOTelefono()) {
            event.preventDefault();
            if (Modal && modalEditarEl) Modal.getOrCreateInstance(modalEditarEl).hide();
            if (Modal && modalConfirmarPersonaEl) Modal.getOrCreateInstance(modalConfirmarPersonaEl).show();
        }
    });

    var btnConfirmar = document.getElementById('btn-confirmar-cambio-persona');
    if (btnConfirmar) {
        btnConfirmar.addEventListener('click', function () {
            if (Modal && modalConfirmarPersonaEl) Modal.getOrCreateInstance(modalConfirmarPersonaEl).hide();
            formEditar.dataset.confirmado = 'true';
            formEditar.requestSubmit();
        });
    }

    var btnCancelar = document.getElementById('btn-cancelar-cambio-persona');
    if (btnCancelar) {
        btnCancelar.addEventListener('click', function () {
            if (Modal && modalConfirmarPersonaEl) Modal.getOrCreateInstance(modalConfirmarPersonaEl).hide();
            if (Modal && modalEditarEl) Modal.getOrCreateInstance(modalEditarEl).show();
        });
    }

    // Reabrir el modal si el servidor devolvio errores para ESTE
    // contacto en concreto (ver 'editar_contacto_id' en views.py). Los
    // campos ya vienen server-renderizados con lo que se envio y fallo
    // -- aqui solo se recupera el "original" (del boton de esa fila,
    // que sigue en el DOM) para que la comparacion de cambios siga
    // funcionando si se reenvia.
    if (formEditar.dataset.abrirModal === 'true') {
        var boton = document.querySelector(
            '[data-editar-contacto][data-contacto-id="' + formEditar.dataset.contactoId + '"]'
        );
        if (boton) {
            original.nombres = boton.dataset.nombres;
            original.apellidos = boton.dataset.apellidos;
            original.telefono = boton.dataset.telefono;
        }
        actualizarParentescoOtroEditar();
        if (Modal && modalEditarEl) Modal.getOrCreateInstance(modalEditarEl).show();
    }
})();

})();
