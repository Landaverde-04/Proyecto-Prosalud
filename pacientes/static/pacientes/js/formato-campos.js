/* Formato automatico de campos mientras se escribe, compartido por
   registrar-paciente.js (telefono, DUI) y registrar-preconsulta.js
   (presion arterial, talla) -- extraido de registrar-paciente.js al
   necesitarse por segunda vez (mismo criterio que buscador-contacto.js).

   Se guarda la posicion del cursor porque insertar un separador sin
   ajustarla lo manda al final cada vez que se teclea. */
/* DUI: 00000000-0. Lo usan el registro de paciente y el modal de registrar DUI. */
function formatearDui(valor) {
    var digitos = valor.replace(/\D/g, '').slice(0, 9);
    return digitos.length > 8 ? digitos.slice(0, 8) + '-' + digitos.slice(8) : digitos;
}

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
