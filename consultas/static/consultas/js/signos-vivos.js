/* Signos vitales en vivo durante la atencion: cada 30s vuelve a pedir la
   tarjeta y, si enfermeria corrigio la preconsulta, reemplaza solo ese
   bloque. No recarga la pagina, asi no se toca lo que se esta escribiendo. */
(function () {
    var CADA_MS = 30000;

    var bloque = document.querySelector('[data-signos-vivos]');
    if (!bloque) return;
    var contenido = bloque.querySelector('[data-signos-contenido]');
    var aviso = bloque.querySelector('[data-signos-aviso]');

    function version(elemento) {
        var marca = elemento.querySelector('[data-signos-version]');
        return marca ? marca.getAttribute('data-signos-version') : '';
    }

    function revisar() {
        // Sin pedir nada mientras la pestaña no se ve.
        if (document.hidden) return;
        fetch(bloque.dataset.url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function (resp) {
                // Sesion vencida u otro error: se deja lo que hay y no se navega,
                // para no sacar al medico de la pantalla a mitad de la consulta.
                if (resp.redirected || !resp.ok) throw new Error('respuesta no valida');
                return resp.text();
            })
            .then(function (html) {
                var nuevo = document.createElement('div');
                nuevo.innerHTML = html;
                if (version(nuevo) === version(contenido)) return;
                contenido.innerHTML = html;
                if (aviso) aviso.hidden = false;
                // border-0 de Bootstrap gana a border: hay que quitarlo para resaltar.
                var tarjeta = bloque.closest('.card');
                if (tarjeta) tarjeta.classList.replace('border-0', 'border-warning');
                if (tarjeta) tarjeta.classList.add('border');
            })
            .catch(function () {
                // Un fallo puntual no rompe nada: se reintenta en el siguiente ciclo.
            });
    }

    setInterval(revisar, CADA_MS);
})();
