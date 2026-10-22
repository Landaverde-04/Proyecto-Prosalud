/*
 * Zonas a tratar -- HU-EST-03.
 *
 * El dibujo de la ficha en papel (cara, frente y espalda). Tocar la figura
 * pone una X numerada; debajo, cada marca tiene su nota y su botón de
 * borrar. Las marcas viajan como JSON en el campo oculto `marcas` y el
 * preguardado (preguardado.js) las guarda solas, como el resto.
 *
 * x e y se guardan como porcentaje de la imagen: así la marca cae en el
 * mismo punto en una pantalla grande o en una tableta.
 */
(function () {
    'use strict';

    var figura = document.getElementById('figura');
    var campo = document.querySelector('input[name=marcas]');
    var lista = document.getElementById('lista-marcas');
    if (!figura || !campo || !lista) { return; }

    var imagen = figura.querySelector('img');
    // Atención finalizada: los campos vienen deshabilitados y solo se mira.
    var soloLectura = campo.disabled;
    var LARGO_NOTA = 150;

    var marcas;
    try { marcas = JSON.parse(campo.value || '[]'); } catch (e) { marcas = []; }
    if (!Array.isArray(marcas)) { marcas = []; }

    // Avisa al preguardado como si se hubiera escrito en un campo.
    function avisarCambio() {
        campo.value = JSON.stringify(marcas);
        campo.dispatchEvent(new Event('input', {bubbles: true}));
    }

    function dibujarMarcas() {
        figura.querySelectorAll('[data-marca]').forEach(function (x) { x.remove(); });
        marcas.forEach(function (marca, indice) {
            var x = document.createElement('span');
            x.setAttribute('data-marca', '');
            x.className = 'position-absolute fw-bold text-danger lh-1 user-select-none';
            x.style.left = marca.x + '%';
            x.style.top = marca.y + '%';
            x.style.transform = 'translate(-50%, -50%)';
            x.style.fontSize = '1.25rem';
            x.style.pointerEvents = 'none';
            x.style.textShadow = '0 0 3px #fff, 0 0 3px #fff';
            x.textContent = '✕';
            var numero = document.createElement('sup');
            numero.textContent = indice + 1;
            numero.style.fontSize = '0.7rem';
            x.appendChild(numero);
            figura.appendChild(x);
        });
    }

    function dibujarLista() {
        lista.innerHTML = '';
        if (!marcas.length) {
            var vacio = document.createElement('li');
            vacio.className = 'small text-muted';
            vacio.textContent = 'Sin zonas marcadas.';
            lista.appendChild(vacio);
            return;
        }
        marcas.forEach(function (marca, indice) {
            var renglon = document.createElement('li');
            renglon.className = 'd-flex align-items-center gap-2';

            var numero = document.createElement('span');
            numero.className = 'fw-bold text-danger text-nowrap';
            numero.textContent = '✕ ' + (indice + 1);
            renglon.appendChild(numero);

            if (soloLectura) {
                var texto = document.createElement('span');
                texto.className = 'small';
                texto.textContent = marca.nota || 'Sin nota';
                renglon.appendChild(texto);
            } else {
                var nota = document.createElement('input');
                nota.type = 'text';
                nota.className = 'form-control form-control-sm';
                nota.maxLength = LARGO_NOTA;
                nota.placeholder = 'Nota de esta zona';
                nota.value = marca.nota || '';
                nota.setAttribute('aria-label', 'Nota de la marca ' + (indice + 1));
                nota.addEventListener('input', function () {
                    marcas[indice].nota = nota.value;
                    avisarCambio();
                });
                renglon.appendChild(nota);

                var borrar = document.createElement('button');
                borrar.type = 'button';
                borrar.className = 'btn btn-sm btn-outline-danger text-nowrap';
                borrar.textContent = 'Borrar';
                borrar.addEventListener('click', function () {
                    marcas.splice(indice, 1);
                    avisarCambio();
                    dibujarTodo();
                });
                renglon.appendChild(borrar);
            }
            lista.appendChild(renglon);
        });
    }

    function dibujarTodo() {
        dibujarMarcas();
        dibujarLista();
    }

    if (!soloLectura) {
        imagen.addEventListener('click', function (evento) {
            var caja = imagen.getBoundingClientRect();
            var x = (evento.clientX - caja.left) / caja.width * 100;
            var y = (evento.clientY - caja.top) / caja.height * 100;
            marcas.push({x: Math.round(x * 100) / 100, y: Math.round(y * 100) / 100, nota: ''});
            avisarCambio();
            dibujarTodo();
            // Lista para escribir la nota de la marca recién puesta.
            var notas = lista.querySelectorAll('input');
            if (notas.length) { notas[notas.length - 1].focus({preventScroll: true}); }
        });
    }

    // Cambiar la figura (Mujer / Hombre) cambia la imagen; las marcas se
    // quedan, porque las dos imágenes tienen el mismo acomodo.
    document.querySelectorAll('input[name=figura]').forEach(function (opcion) {
        opcion.addEventListener('change', function () {
            imagen.src = opcion.value === 'hombre' ? figura.dataset.imgHombre : figura.dataset.imgMujer;
        });
    });

    dibujarTodo();
})();
