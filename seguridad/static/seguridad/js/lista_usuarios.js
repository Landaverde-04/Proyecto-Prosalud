(function () {
    var input         = document.getElementById('buscador');
    var tbody         = document.getElementById('tabla-cuerpo');
    var sinResultados = document.getElementById('sin-resultados');

    if (!input || !tbody) return;

    var filas     = Array.from(tbody.querySelectorAll('tr'));
    var colActiva = -1;
    var direccion = 'asc';

    /* ── Ordenar al hacer clic en cabecera ── */
    document.querySelectorAll('th[data-sort]').forEach(function (th) {
        th.addEventListener('click', function () {
            var col = parseInt(this.dataset.sort);
            if (colActiva === col) {
                direccion = direccion === 'asc' ? 'desc' : 'asc';
            } else {
                colActiva = col;
                direccion = 'asc';
            }
            actualizarIconos();
            renderizar();
        });
    });

    function actualizarIconos() {
        document.querySelectorAll('th[data-sort]').forEach(function (th) {
            var icono = th.querySelector('.sort-icon');
            var col   = parseInt(th.dataset.sort);
            if (col === colActiva) {
                icono.className = 'sort-icon ms-1 bi ' + (direccion === 'asc' ? 'bi-arrow-up' : 'bi-arrow-down');
                icono.style.opacity = '1';
            } else {
                icono.className = 'sort-icon ms-1 bi bi-arrow-down-up opacity-50';
                icono.style.opacity = '';
            }
        });
    }

    /* ── Buscar al escribir (desde 2 caracteres) ── */
    input.addEventListener('input', renderizar);

    function renderizar() {
        var consulta      = input.value.trim().toLowerCase();
        var aplicarFiltro = consulta.length >= 2;

        var visibles = filas.filter(function (fila) {
            if (!aplicarFiltro) return true;
            return (fila.dataset.search || '').toLowerCase().includes(consulta);
        });

        if (colActiva >= 0) {
            visibles.sort(function (a, b) {
                var va = a.cells[colActiva] ? a.cells[colActiva].textContent.trim().toLowerCase() : '';
                var vb = b.cells[colActiva] ? b.cells[colActiva].textContent.trim().toLowerCase() : '';
                var r  = va.localeCompare(vb, 'es');
                return direccion === 'asc' ? r : -r;
            });
        }

        filas.forEach(function (f) { f.style.display = 'none'; });
        visibles.forEach(function (f) {
            f.style.display = '';
            tbody.appendChild(f);
        });

        sinResultados.style.display = (visibles.length === 0 && aplicarFiltro) ? '' : 'none';
    }
})();
