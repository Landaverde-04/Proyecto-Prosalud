/*
 * Zonas a tratar -- HU-EST-03.
 *
 * El dibujo de la ficha en papel (cara, frente y espalda). Arriba se elige
 * qué dibujar:
 *   - Punto: tocar la figura pone un punto numerado.
 *   - Flecha: arrastrar desde un punto dibuja una flecha (vector) hacia donde
 *     irradia; de un mismo punto salen varias. Arrastrar desde un lugar
 *     vacío crea el punto y la flecha de una vez.
 * Debajo, cada punto tiene su nota, "Quitar última flecha" y "Borrar".
 *
 * Se dibuja en una capa SVG encima de la imagen, con las mismas medidas de
 * la imagen: así las flechas no se deforman en ninguna pantalla. Los datos
 * viajan como JSON en el campo oculto `marcas`, con x e y en porcentaje, y
 * el preguardado (preguardado.js) los guarda solos.
 */
(function () {
    'use strict';

    var figura = document.getElementById('figura');
    var campo = document.querySelector('input[name=marcas]');
    var lista = document.getElementById('lista-marcas');
    if (!figura || !campo || !lista) { return; }

    var imagen = figura.querySelector('img');
    var SVG = 'http://www.w3.org/2000/svg';
    // Atención finalizada: los campos vienen deshabilitados y solo se mira.
    var soloLectura = campo.disabled;
    var LARGO_NOTA = 150;
    var MAXIMO_VECTORES = 12;
    var COLOR = '#c0392b';
    // Distancia en pantalla por debajo de la cual un arrastre es un toque, y
    // radio para "atinarle" a un punto existente.
    var UMBRAL_ARRASTRE = 8;
    var RADIO_ATINAR = 16;

    var marcas;
    try { marcas = JSON.parse(campo.value || '[]'); } catch (e) { marcas = []; }
    if (!Array.isArray(marcas)) { marcas = []; }
    marcas.forEach(function (marca) { if (!Array.isArray(marca.vectores)) { marca.vectores = []; } });

    var ancho = 100;
    var alto = 100;
    var capa = document.createElementNS(SVG, 'svg');
    capa.setAttribute('class', 'position-absolute top-0 start-0 w-100 h-100');
    capa.style.touchAction = 'none';
    if (!soloLectura) { capa.style.cursor = 'crosshair'; }
    figura.appendChild(capa);

    // Avisa al preguardado como si se hubiera escrito en un campo.
    function avisarCambio() {
        campo.value = JSON.stringify(marcas);
        campo.dispatchEvent(new Event('input', {bubbles: true}));
    }

    function porcentaje(evento) {
        var caja = capa.getBoundingClientRect();
        return {
            x: Math.min(100, Math.max(0, Math.round((evento.clientX - caja.left) / caja.width * 10000) / 100)),
            y: Math.min(100, Math.max(0, Math.round((evento.clientY - caja.top) / caja.height * 10000) / 100)),
        };
    }

    function aPixeles(punto) {
        return {x: punto.x / 100 * ancho, y: punto.y / 100 * alto};
    }

    function elemento(nombre, atributos) {
        var nodo = document.createElementNS(SVG, nombre);
        Object.keys(atributos).forEach(function (clave) { nodo.setAttribute(clave, atributos[clave]); });
        return nodo;
    }

    function flecha(desde, hasta) {
        var a = aPixeles(desde);
        var b = aPixeles(hasta);
        return elemento('line', {
            x1: a.x, y1: a.y, x2: b.x, y2: b.y, stroke: COLOR,
            'stroke-width': ancho * 0.003, 'stroke-linecap': 'round', 'marker-end': 'url(#punta)',
        });
    }

    function dibujarCapa() {
        capa.innerHTML = '';
        var definiciones = elemento('defs', {});
        var punta = elemento('marker', {
            id: 'punta', viewBox: '0 0 10 10', refX: 8, refY: 5,
            markerWidth: 5, markerHeight: 5, orient: 'auto-start-reverse',
        });
        punta.appendChild(elemento('path', {d: 'M 0 0 L 10 5 L 0 10 z', fill: COLOR}));
        definiciones.appendChild(punta);
        capa.appendChild(definiciones);

        var radio = ancho * 0.006;
        marcas.forEach(function (marca, indice) {
            marca.vectores.forEach(function (vector) { capa.appendChild(flecha(marca, vector)); });
            var centro = aPixeles(marca);
            capa.appendChild(elemento('circle', {
                cx: centro.x, cy: centro.y, r: radio, fill: COLOR, stroke: '#fff', 'stroke-width': radio * 0.35,
            }));
            var numero = elemento('text', {
                x: centro.x + radio * 1.4, y: centro.y - radio * 1.2, fill: COLOR,
                'font-size': radio * 2.6, 'font-weight': 'bold', stroke: '#fff', 'stroke-width': radio * 0.3,
                'paint-order': 'stroke',
            });
            numero.textContent = indice + 1;
            capa.appendChild(numero);
        });
    }

    function boton(texto, clase, accion) {
        var nuevo = document.createElement('button');
        nuevo.type = 'button';
        nuevo.className = 'btn btn-sm text-nowrap ' + clase;
        nuevo.textContent = texto;
        nuevo.addEventListener('click', accion);
        return nuevo;
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
            renglon.className = 'd-flex align-items-center flex-wrap gap-2';

            var numero = document.createElement('span');
            numero.className = 'fw-bold text-nowrap';
            numero.style.color = COLOR;
            numero.textContent = '● ' + (indice + 1);
            renglon.appendChild(numero);

            var flechas = marca.vectores.length;
            var cuantas = flechas ? ' · ' + flechas + (flechas === 1 ? ' flecha' : ' flechas') : '';

            if (soloLectura) {
                var texto = document.createElement('span');
                texto.className = 'small';
                texto.textContent = (marca.nota || 'Sin nota') + cuantas;
                renglon.appendChild(texto);
                lista.appendChild(renglon);
                return;
            }

            var nota = document.createElement('input');
            nota.type = 'text';
            nota.className = 'form-control form-control-sm flex-grow-1';
            nota.style.minWidth = '160px';
            nota.style.width = 'auto';
            nota.maxLength = LARGO_NOTA;
            nota.placeholder = 'Nota de esta zona';
            nota.value = marca.nota || '';
            nota.setAttribute('aria-label', 'Nota del punto ' + (indice + 1));
            nota.addEventListener('input', function () {
                marcas[indice].nota = nota.value;
                avisarCambio();
            });
            renglon.appendChild(nota);

            if (flechas) {
                renglon.appendChild(boton('Quitar última flecha', 'btn-outline-secondary', function () {
                    marcas[indice].vectores.pop();
                    avisarCambio();
                    dibujarTodo();
                }));
            }
            renglon.appendChild(boton('Borrar', 'btn-outline-danger', function () {
                marcas.splice(indice, 1);
                avisarCambio();
                dibujarTodo();
            }));
            lista.appendChild(renglon);
        });
    }

    function dibujarTodo() {
        dibujarCapa();
        dibujarLista();
    }

    // El punto más cercano al toque, si cae dentro del radio para atinarle.
    function puntoCercano(evento) {
        var caja = capa.getBoundingClientRect();
        var mejor = -1;
        var distancia = RADIO_ATINAR;
        marcas.forEach(function (marca, indice) {
            var dx = caja.left + marca.x / 100 * caja.width - evento.clientX;
            var dy = caja.top + marca.y / 100 * caja.height - evento.clientY;
            var d = Math.sqrt(dx * dx + dy * dy);
            if (d <= distancia) { distancia = d; mejor = indice; }
        });
        return mejor;
    }

    if (!soloLectura) {
        var trazo = null;
        var modo = 'punto';
        var AYUDAS = {
            punto: 'Toque la figura donde va el punto.',
            flecha: 'Arrastre desde un punto hacia donde irradia.',
        };
        var selector = document.getElementById('modo-marcas');
        var ayuda = document.getElementById('ayuda-marcas');
        if (selector) {
            selector.addEventListener('click', function (evento) {
                var elegido = evento.target.closest('[data-modo]');
                if (!elegido) { return; }
                modo = elegido.dataset.modo;
                selector.querySelectorAll('[data-modo]').forEach(function (opcion) {
                    var activo = opcion === elegido;
                    opcion.classList.toggle('active', activo);
                    opcion.setAttribute('aria-pressed', activo ? 'true' : 'false');
                });
                if (ayuda) { ayuda.textContent = AYUDAS[modo]; }
            });
        }

        capa.addEventListener('pointerdown', function (evento) {
            evento.preventDefault();
            capa.setPointerCapture(evento.pointerId);
            trazo = {
                origen: puntoCercano(evento), inicio: porcentaje(evento),
                x: evento.clientX, y: evento.clientY, linea: null,
            };
        });

        capa.addEventListener('pointermove', function (evento) {
            if (!trazo || modo !== 'flecha') { return; }
            var movido = Math.abs(evento.clientX - trazo.x) + Math.abs(evento.clientY - trazo.y);
            if (movido < UMBRAL_ARRASTRE) { return; }
            var desde = trazo.origen >= 0 ? marcas[trazo.origen] : trazo.inicio;
            if (trazo.linea) { trazo.linea.remove(); }
            trazo.linea = flecha(desde, porcentaje(evento));
            trazo.linea.setAttribute('stroke-dasharray', ancho * 0.006);
            capa.appendChild(trazo.linea);
        });

        capa.addEventListener('pointerup', function (evento) {
            if (!trazo) { return; }
            var actual = trazo;
            trazo = null;
            var movido = Math.abs(evento.clientX - actual.x) + Math.abs(evento.clientY - actual.y);

            if (modo === 'punto') {
                // En un punto existente no hace nada (se edita abajo); en un
                // lugar vacío, punto nuevo. Un pulso tembloroso no importa.
                if (actual.origen < 0) {
                    marcas.push({x: actual.inicio.x, y: actual.inicio.y, nota: '', vectores: []});
                    avisarCambio();
                    dibujarTodo();
                    var notas = lista.querySelectorAll('input');
                    if (notas.length) { notas[notas.length - 1].focus({preventScroll: true}); }
                } else {
                    dibujarCapa();
                }
                return;
            }

            // Flecha: un toque sin arrastrar no dibuja nada.
            if (movido < UMBRAL_ARRASTRE) {
                dibujarCapa();
                if (ayuda) { ayuda.textContent = AYUDAS.flecha; }
                return;
            }

            // Arrastre: flecha desde el punto tocado, o punto nuevo + flecha.
            var indice = actual.origen;
            if (indice < 0) {
                marcas.push({x: actual.inicio.x, y: actual.inicio.y, nota: '', vectores: []});
                indice = marcas.length - 1;
            }
            if (marcas[indice].vectores.length < MAXIMO_VECTORES) {
                marcas[indice].vectores.push(porcentaje(evento));
            } else if (window.avisar) {
                window.avisar('Cada punto puede tener hasta ' + MAXIMO_VECTORES + ' flechas.', 'warning');
            }
            avisarCambio();
            dibujarTodo();
        });

        capa.addEventListener('pointercancel', function () {
            trazo = null;
            dibujarCapa();
        });
    }

    // Cambiar la figura (Mujer / Hombre) cambia la imagen; las marcas se
    // quedan, porque las dos imágenes tienen el mismo acomodo.
    document.querySelectorAll('input[name=figura]').forEach(function (opcion) {
        opcion.addEventListener('change', function () {
            imagen.src = opcion.value === 'hombre' ? figura.dataset.imgHombre : figura.dataset.imgMujer;
        });
    });

    // La capa usa las medidas reales de la imagen para que nada se deforme.
    function preparar() {
        ancho = imagen.naturalWidth || 100;
        alto = imagen.naturalHeight || 100;
        capa.setAttribute('viewBox', '0 0 ' + ancho + ' ' + alto);
        dibujarTodo();
    }
    if (imagen.complete && imagen.naturalWidth) { preparar(); } else { imagen.addEventListener('load', preparar); }
    dibujarLista();
})();
