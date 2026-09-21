document.addEventListener('DOMContentLoaded', function () {
    /* ---- IMC en vivo ---- */
    var peso = document.getElementById('id_peso');
    var talla = document.getElementById('id_talla');
    var salidaImc = document.getElementById('imc-calculado');

    function actualizarImc() {
        if (!peso || !talla || !salidaImc) return;
        var p = parseFloat(peso.value);
        var t = parseFloat(talla.value);
        if (p > 0 && t > 0) {
            salidaImc.textContent = (p / (t * t)).toFixed(1);
        } else {
            salidaImc.textContent = '—';
        }
    }

    /* ---- Formato automatico: talla (1.20) y presion arterial (120/80) ----
       conCursorFijo() vive en formato-campos.js, que debe cargarse antes
       que este script. */
    function formatearTalla(valor) {
        var digitos = valor.replace(/\D/g, '').slice(0, 3);
        return digitos.length > 1 ? digitos.slice(0, 1) + '.' + digitos.slice(1) : digitos;
    }

    function formatearPresion(valor) {
        var digitos = valor.replace(/\D/g, '').slice(0, 5);
        return digitos.length > 3 ? digitos.slice(0, 3) + '/' + digitos.slice(3) : digitos;
    }

    if (talla) {
        // Este listener va antes para que el IMC se calcule ya con el valor formateado.
        conCursorFijo(talla, formatearTalla);
        talla.addEventListener('input', actualizarImc);
    }
    if (peso) peso.addEventListener('input', actualizarImc);
    // Con valores ya cargados (al editar, o tras un error del servidor) el IMC se ve de entrada.
    actualizarImc();

    var presion = document.getElementById('id_presion_arterial');
    if (presion) conCursorFijo(presion, formatearPresion);

    function llevarA(elemento, foco) {
        elemento.scrollIntoView({ behavior: 'smooth', block: 'center' });
        if (foco) foco.focus({ preventScroll: true });
    }

    /* ---- Emergencia: el motivo solo aparece si se marca ---- */
    var checkEmergencia = document.getElementById('id_es_emergencia');
    var campoMotivo = document.getElementById('campo-motivo-emergencia');
    var bloqueEmergencia = document.getElementById('bloque-emergencia');
    var inputMotivo = document.getElementById('id_motivo_prioridad');
    if (checkEmergencia && campoMotivo && inputMotivo) {
        checkEmergencia.addEventListener('change', function () {
            campoMotivo.classList.toggle('d-none', !checkEmergencia.checked);
            if (bloqueEmergencia) bloqueEmergencia.classList.toggle('border-danger', checkEmergencia.checked);
            if (checkEmergencia.checked) inputMotivo.focus();
        });
        // En cuanto escribe algo, se quita el rojo: el aviso ya cumplio.
        inputMotivo.addEventListener('input', function () {
            if (inputMotivo.value.trim()) inputMotivo.classList.remove('is-invalid');
        });
    }

    /* ---- Chequeo antes de enviar ----
       El formulario tiene novalidate, asi que el navegador no avisa nada por
       su cuenta. Se revisa en el orden de la pantalla y se lleva a la
       persona al primer problema, sin recargar ni perder lo escrito. */
    var formulario = document.getElementById('form-preconsulta');
    var seccionMedico = document.getElementById('seccion-medico');
    var avisoMedico = document.getElementById('aviso-medico-cliente');

    if (formulario) {
        formulario.addEventListener('submit', function (evento) {
            if (checkEmergencia && checkEmergencia.checked && !inputMotivo.value.trim()) {
                evento.preventDefault();
                inputMotivo.classList.add('is-invalid');
                llevarA(bloqueEmergencia || inputMotivo, inputMotivo);
                return;
            }
            var hayMedicos = formulario.querySelectorAll('input[name="medico"]').length > 0;
            var elegido = formulario.querySelector('input[name="medico"]:checked');
            if (seccionMedico && hayMedicos && !elegido) {
                evento.preventDefault();
                if (avisoMedico) avisoMedico.classList.remove('d-none');
                llevarA(seccionMedico);
            }
        });

        // Errores que vienen del servidor (rangos, formato, o si JS falla):
        // el POST recarga la pagina arriba del todo, asi que se baja solo al
        // primero en vez de dejar que la persona lo busque.
        var primerError = formulario.querySelector('.is-invalid, [data-error-servidor]');
        if (primerError) {
            var esCampo = primerError.matches('input, select, textarea');
            llevarA(esCampo ? (primerError.closest('.mb-3, .col-sm-6, #bloque-emergencia') || primerError) : seccionMedico,
                    esCampo ? primerError : null);
        }
    }
});
