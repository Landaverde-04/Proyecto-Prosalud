/* Modal "Registrar DUI": toma del boton que lo abrio la URL, el nombre y los
   responsables. Escucha el evento del modal, no el clic del boton, porque en
   la lista los botones se reemplazan con cada busqueda.
   formatearDui() y conCursorFijo() vienen de formato-campos.js. */
document.addEventListener('DOMContentLoaded', function () {
    var modal = document.getElementById('modalRegistrarDui');
    if (!modal) return;
    var formulario = modal.querySelector('form');
    var campo = modal.querySelector('#duiNuevo');
    var nombre = modal.querySelector('[data-dui-nombre]');
    var bloqueResponsables = modal.querySelector('[data-dui-con-responsables]');
    var responsables = modal.querySelector('[data-dui-responsables]');

    conCursorFijo(campo, formatearDui);

    modal.addEventListener('show.bs.modal', function (evento) {
        var boton = evento.relatedTarget;
        if (!boton) return;
        formulario.action = boton.dataset.url;
        nombre.textContent = boton.dataset.nombre;
        campo.value = '';
        var lista = boton.dataset.responsables || '';
        responsables.textContent = lista;
        bloqueResponsables.hidden = !lista;
    });

    modal.addEventListener('shown.bs.modal', function () {
        campo.focus();
    });
});
