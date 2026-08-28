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

    /* ── Modal de confirmacion de eliminacion ── */
    var modalEliminarEl = document.getElementById('modalEliminar');
    if (modalEliminarEl) {
        document.addEventListener('click', function (event) {
            var btn = event.target.closest('[data-accion="eliminar"]');
            if (!btn) return;

            var nombre   = btn.dataset.nombre   || '';
            var url      = btn.dataset.url      || '';
            var tipo     = btn.dataset.tipo     || 'elemento';
            var usuarios = parseInt(btn.dataset.usuarios || '0');

            document.getElementById('modal-eliminar-titulo').textContent =
                'Eliminar ' + tipo;

            var preguntaEl = document.getElementById('modal-eliminar-pregunta');
            preguntaEl.innerHTML = '';
            preguntaEl.appendChild(document.createTextNode(
                '¿Estas seguro de que deseas eliminar ' +
                (tipo === 'usuario' ? 'al usuario ' : 'el rol ')
            ));
            var fuerte = document.createElement('strong');
            fuerte.textContent = nombre;
            preguntaEl.appendChild(fuerte);
            preguntaEl.appendChild(document.createTextNode('?'));

            var avisoEl = document.getElementById('modal-eliminar-aviso');
            if (tipo === 'rol' && usuarios > 0) {
                avisoEl.textContent = 'Este rol tiene ' + usuarios +
                    ' usuario' + (usuarios !== 1 ? 's' : '') +
                    ' asignados. Seran desvinculados del rol.';
                avisoEl.style.display = '';
            } else {
                avisoEl.style.display = 'none';
            }

            document.getElementById('form-modal-eliminar').action = url;
            mostrarModal(modalEliminarEl);
        });
    }

});
