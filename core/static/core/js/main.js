document.addEventListener('DOMContentLoaded', function () {

    /* ── Sidebar ── */
    var sidebar       = document.getElementById('sidebar');
    var backdrop      = document.getElementById('sidebar-backdrop');
    var btnToggle     = document.getElementById('sidebar-toggle');
    var btnOpenMobile = document.getElementById('sidebar-open-mobile');

    function esMobile() {
        return window.innerWidth < 768;
    }

    function abrirMobile() {
        sidebar.classList.add('sidebar-open');
        backdrop.classList.add('show');
        document.body.style.overflow = 'hidden';
    }

    function cerrarMobile() {
        sidebar.classList.remove('sidebar-open');
        backdrop.classList.remove('show');
        document.body.style.overflow = '';
    }

    if (btnToggle) {
        btnToggle.addEventListener('click', function () {
            if (esMobile()) {
                cerrarMobile();
            } else {
                var colapsado = sidebar.classList.toggle('sidebar-collapsed');
                localStorage.setItem('sidebar-colapsado', colapsado ? '1' : '0');
            }
        });
    }

    if (btnOpenMobile) {
        btnOpenMobile.addEventListener('click', abrirMobile);
    }

    if (backdrop) {
        backdrop.addEventListener('click', cerrarMobile);
    }

    // Restaurar estado colapsado en escritorio
    if (sidebar && !esMobile() && localStorage.getItem('sidebar-colapsado') === '1') {
        sidebar.classList.add('sidebar-collapsed');
    }

    /* ── Toggle visibilidad de contraseña ── */
    document.addEventListener('click', function (e) {
        var btn = e.target.closest('.toggle-password');
        if (!btn) return;
        var input = document.getElementById(btn.dataset.target);
        if (!input) return;
        var icono = btn.querySelector('i');
        if (input.type === 'password') {
            input.type = 'text';
            icono.className = 'bi bi-eye-slash';
        } else {
            input.type = 'password';
            icono.className = 'bi bi-eye';
        }
    });

    /* ── Modales ── */

    function mostrarModal(el) {
        el.style.display = 'block';
        el.classList.add('show');
        document.body.classList.add('modal-open');
        var bd = document.createElement('div');
        bd.className = 'modal-backdrop fade show';
        bd.setAttribute('data-para', el.id);
        document.body.appendChild(bd);
        bd.addEventListener('click', function () { ocultarModal(el); });
    }

    function ocultarModal(el) {
        el.style.display = 'none';
        el.classList.remove('show');
        document.body.classList.remove('modal-open');
        var bd = document.querySelector('[data-para="' + el.id + '"]');
        if (bd) bd.remove();
    }

    document.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-bs-dismiss="modal"]');
        if (btn) {
            var modal = btn.closest('.modal');
            if (modal) ocultarModal(modal);
        }
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal.show').forEach(function (modal) {
                ocultarModal(modal);
            });
        }
    });

    /* ── Modal de mensajes del sistema ── */
    var modalMensaje = document.getElementById('modalMensaje');
    if (modalMensaje) {
        mostrarModal(modalMensaje);
    }

    /* ── Modal de confirmacion generico ──

       Se dispara desde cualquier boton con data-confirmar. Atributos:
         data-titulo   -- encabezado del modal
         data-mensaje  -- texto antes del nombre (que va en negrita)
         data-nombre   -- nombre del elemento afectado
         data-boton    -- etiqueta del boton que confirma
         data-color    -- danger | warning | success (encabezado y boton)
         data-icono    -- clase de Bootstrap Icons, ej: bi-trash-fill
         data-aviso    -- (opcional) advertencia en amarillo
         data-nota     -- (opcional) nota gris al pie
         data-url      -- destino del POST
    */
    var modalConfirmarEl = document.getElementById('modalConfirmar');
    if (modalConfirmarEl) {
        document.addEventListener('click', function (event) {
            var btn = event.target.closest('[data-confirmar]');
            if (!btn) return;

            var color = btn.dataset.color || 'danger';

            // bg-warning es amarillo claro: ahi el texto blanco no se lee
            var fondoClaro = (color === 'warning');

            var encabezado = document.getElementById('modal-confirmar-encabezado');
            encabezado.className = 'modal-header border-0 bg-' + color +
                (fondoClaro ? ' text-dark' : ' text-white');

            var btnCerrar = encabezado.querySelector('.btn-close');
            btnCerrar.className = 'btn-close' + (fondoClaro ? '' : ' btn-close-white');

            document.getElementById('modal-confirmar-icono').className =
                'bi fs-5 ' + (btn.dataset.icono || 'bi-question-circle-fill');

            document.getElementById('modal-confirmar-titulo').textContent =
                btn.dataset.titulo || 'Confirmar';

            // Se arma con textContent (no innerHTML) para que un nombre con
            // caracteres raros no pueda inyectar HTML
            var preguntaEl = document.getElementById('modal-confirmar-pregunta');
            preguntaEl.textContent = '';
            preguntaEl.appendChild(document.createTextNode(btn.dataset.mensaje || ''));
            if (btn.dataset.nombre) {
                var fuerte = document.createElement('strong');
                fuerte.textContent = btn.dataset.nombre;
                preguntaEl.appendChild(fuerte);
                preguntaEl.appendChild(document.createTextNode('?'));
            }

            var avisoEl = document.getElementById('modal-confirmar-aviso');
            if (btn.dataset.aviso) {
                avisoEl.textContent = btn.dataset.aviso;
                avisoEl.style.display = '';
            } else {
                avisoEl.style.display = 'none';
            }

            var notaEl = document.getElementById('modal-confirmar-nota');
            if (btn.dataset.nota) {
                notaEl.textContent = btn.dataset.nota;
                notaEl.style.display = '';
            } else {
                notaEl.style.display = 'none';
            }

            var botonEl = document.getElementById('modal-confirmar-boton');
            botonEl.className = 'btn btn-sm btn-' + color;
            botonEl.textContent = btn.dataset.boton || 'Confirmar';

            document.getElementById('form-modal-confirmar').action = btn.dataset.url || '';
            mostrarModal(modalConfirmarEl);
        });
    }

});
