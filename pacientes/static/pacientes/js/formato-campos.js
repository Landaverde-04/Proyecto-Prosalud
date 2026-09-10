/* Formato automatico de campos mientras se escribe, compartido por
   registrar-paciente.js (telefono, DUI) y registrar-preconsulta.js
   (presion arterial, talla) -- extraido de registrar-paciente.js al
   necesitarse por segunda vez (mismo criterio que buscador-contacto.js).

   Se guarda la posicion del cursor porque insertar un separador sin
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
