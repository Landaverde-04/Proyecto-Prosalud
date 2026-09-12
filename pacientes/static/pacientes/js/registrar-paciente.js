(function () {
    var form = document.getElementById('form-registrar-paciente');
    if (!form) return;

    var urlBuscar = form.dataset.buscarPersonaUrl;

    /* ---- Interruptor Adulto/Menor: solo cambia textos en pantalla.
       La decision real de si es menor la hace el servidor con la fecha
       de nacimiento (ver RegistrarPacienteForm.clean()) -- este radio
       nunca se lee en el backend, name="tipo_paciente_ui" no es un
       campo del formulario de Django. ---- */
    var radioAdulto = document.getElementById('tipo-adulto');
    var radioMenor = document.getElementById('tipo-menor');
    var tituloSeccionContacto = document.getElementById('titulo-seccion-contacto');
    var etiquetaSeccionContacto = document.getElementById('etiqueta-seccion-contacto');
    var ayudaSeccionContacto = document.getElementById('ayuda-seccion-contacto');
    var seccionContactoDiv = document.getElementById('seccion-contacto');
    var etiquetaTelefonoPaciente = document.getElementById('etiqueta-telefono-paciente');
    var campoDui = document.getElementById('id_dui');

    function actualizarModoPaciente() {
        var esMenor = !!(radioMenor && radioMenor.checked);

        if (tituloSeccionContacto) {
            tituloSeccionContacto.textContent = esMenor ? 'Datos del responsable' : 'Contacto de referencia';
        }
        if (etiquetaSeccionContacto) {
            etiquetaSeccionContacto.textContent = esMenor ? '(obligatorio)' : '(opcional)';
        }
        // El telefono del paciente es al reves que el del contacto:
        // obligatorio para adulto, opcional para menor (ver forms.py).
        if (etiquetaTelefonoPaciente) {
            etiquetaTelefonoPaciente.textContent = esMenor ? '(opcional)' : '(obligatorio)';
        }
        // Un menor de edad no tiene DUI en El Salvador (se emite hasta
        // los 18 anios) -- se deshabilita el campo para que no se
        // pueda escribir uno por error, y se limpia lo que hubiera
        // quedado escrito de cuando el interruptor estaba en "Adulto".
        if (campoDui) {
            campoDui.disabled = esMenor;
            if (esMenor) campoDui.value = '';
        }
        if (ayudaSeccionContacto) {
            ayudaSeccionContacto.textContent = esMenor
                ? 'Todo paciente menor de edad necesita al menos un responsable.'
                : 'Alguien a quien contactar por este paciente. Puedes omitirlo si ahora no lo tienes.';
        }

        // Si pasa a ser menor, la seccion de contacto se abre sola --
        // ahi es obligatoria, no tiene sentido dejarla colapsada.
        // Se usa el API de Bootstrap Collapse (no solo classList) para
        // que el boton quede sincronizado (aria-expanded, ".collapsed").
        if (esMenor && seccionContactoDiv && !seccionContactoDiv.classList.contains('show')) {
            var Collapse = window.bootstrap && window.bootstrap.Collapse;
            if (Collapse) {
                Collapse.getOrCreateInstance(seccionContactoDiv, { toggle: false }).show();
            }
        }
    }

    [radioAdulto, radioMenor].forEach(function (radio) {
        if (radio) radio.addEventListener('change', actualizarModoPaciente);
    });
    if (radioAdulto || radioMenor) actualizarModoPaciente();

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

    /* ---- Edad calculada en vivo (HU-EXP-01: "el sistema calcula la
       edad") y, con ella, el interruptor Adulto/Menor se ajusta solo
       (HU-EXP-02: la fecha de nacimiento sugiere el tipo). ---- */
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

        if (edad !== null && (radioAdulto || radioMenor)) {
            var esMenor = edad < 18;
            if (radioMenor) radioMenor.checked = esMenor;
            if (radioAdulto) radioAdulto.checked = !esMenor;
            actualizarModoPaciente();
        }
    }

    if (campoFecha) {
        campoFecha.addEventListener('change', actualizarEdad);
        actualizarEdad();
    }

    /* ---- Formato automatico: telefono (0000-0000) y DUI (00000000-0) ----
       conCursorFijo() vive en formato-campos.js (compartido con
       registrar-preconsulta.js), que debe cargarse antes que este script. */
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

    /* ---- Buscar y reutilizar un contacto o responsable existente ----
       Logica compartida con el modal de "agregar contacto" del
       expediente (HU-EXP-05/06) -- ver buscador-contacto.js, que debe
       cargarse antes que este script. ---- */
    if (typeof iniciarBuscadorContacto === 'function') {
        iniciarBuscadorContacto({
            urlBuscar: urlBuscar,
            buscador: 'buscador-contacto',
            resultados: 'resultados-contacto',
            bannerVinculado: 'contacto-vinculado',
            nombreVinculado: 'contacto-vinculado-nombre',
            btnDesvincular: 'btn-desvincular-contacto',
            campoId: 'id_contacto_persona_id',
            campoNombres: 'id_contacto_nombres',
            campoApellidos: 'id_contacto_apellidos',
            campoTelefono: 'id_contacto_telefono',
        });
    }
})();
