/* Auto-refresco de la cola: vuelve a pedir el fragmento de resultados
   cada 30s y lo reemplaza, sin recargar la pantalla. El servidor devuelve
   solo ese fragmento cuando ve el header X-Requested-With (mismo patron
   que listado-vivo.js). Si el navegador no ejecuta esto, la cola sigue
   funcionando: se ve el estado del momento en que se abrio. */
(function () {
    var CADA_MS = 30000;

    var resultados = document.querySelector('[data-cola-resultados]');
    if (!resultados) return;
    var aviso = document.getElementById('cola-actualizada');

    function marcarHora() {
        if (!aviso) return;
        var ahora = new Date();
        aviso.textContent =
            String(ahora.getHours()).padStart(2, '0') + ':' +
            String(ahora.getMinutes()).padStart(2, '0');
    }

    function refrescar() {
        // Pausado mientras la pestaña no se ve: no tiene sentido consultar
        // al servidor cada 30s si nadie esta mirando la cola.
        if (document.hidden) return;
        fetch(window.location.href, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function (resp) {
                if (!resp.ok) throw new Error('respuesta no valida');
                return resp.text();
            })
            .then(function (html) {
                resultados.innerHTML = html;
                marcarHora();
            })
            .catch(function () {
                // Un fallo puntual de red no debe romper nada: se deja lo
                // que ya estaba en pantalla y se reintenta al siguiente ciclo.
            });
    }

    marcarHora();
    setInterval(refrescar, CADA_MS);
    // Al volver a la pestaña, refrescar de una vez en vez de esperar el ciclo.
    document.addEventListener('visibilitychange', function () {
        if (!document.hidden) refrescar();
    });
})();
