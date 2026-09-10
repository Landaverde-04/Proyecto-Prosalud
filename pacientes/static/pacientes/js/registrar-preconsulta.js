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

    var presion = document.getElementById('id_presion_arterial');
    if (presion) conCursorFijo(presion, formatearPresion);

    /* ---- Aviso si se intenta enviar sin elegir medico ----
       El formulario tiene novalidate, asi que el "required" del radio no
       dispara el aviso nativo del navegador -- este chequeo lo reemplaza. */
    var formulario = document.getElementById('form-preconsulta');
    var seccionMedico = document.getElementById('seccion-medico');
    var avisoMedico = document.getElementById('aviso-medico-cliente');

    if (formulario && seccionMedico) {
        formulario.addEventListener('submit', function (evento) {
            var hayMedicos = formulario.querySelectorAll('input[name="medico"]').length > 0;
            var elegido = formulario.querySelector('input[name="medico"]:checked');
            if (hayMedicos && !elegido) {
                evento.preventDefault();
                if (avisoMedico) avisoMedico.classList.remove('d-none');
                seccionMedico.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        });
    }

    // Respaldo si el error vino del servidor (JS desactivado): scroll hasta el aviso.
    var avisoServidor = document.getElementById('aviso-medico-servidor');
    if (avisoServidor && seccionMedico) {
        seccionMedico.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
});
