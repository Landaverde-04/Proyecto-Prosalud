/*
 * Aviso NO bloqueante de contrasena corta -- decision de Kevin,
 * 10/09/2026 (ver AUTH_PASSWORD_VALIDATORS en settings.py): ya no se
 * rechaza ninguna contrasena por corta o comun, pero se avisa igual,
 * para que quien la escribe lo sepa y decida.
 *
 * Cualquier campo con data-aviso-password="<id-del-aviso>" se vigila
 * solo -- no hace falta un <script> por pantalla, solo el atributo.
 */
document.addEventListener('DOMContentLoaded', function () {
    var UMBRAL = 8;

    document.querySelectorAll('[data-aviso-password]').forEach(function (campo) {
        var aviso = document.getElementById(campo.dataset.avisoPassword);
        if (!aviso) return;

        function actualizar() {
            var corta = campo.value.length > 0 && campo.value.length < UMBRAL;
            aviso.classList.toggle('d-none', !corta);
        }

        campo.addEventListener('input', actualizar);
        actualizar();
    });
});
