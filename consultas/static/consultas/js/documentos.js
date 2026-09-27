(() => {
    const formulario = document.getElementById('form-documento');
    if (formulario) {
        const opcion = formulario.querySelector('#id_inicio_opcion');
        const fecha = formulario.querySelector('#id_fecha_inicio_incapacidad');
        const dias = formulario.querySelector('#id_dias');
        const resumen = document.getElementById('resumen-reposo');
        function actualizar() {
            dias.required = true;
            fecha.readOnly = opcion.value === 'hoy';
            if (fecha.readOnly) fecha.value = formulario.dataset.hoy;
            fecha.required = true;
            resumen.textContent = 'El inicio cuenta como primer día de reposo.';
            const cantidad = Number(dias.value);
            if (fecha.value && Number.isInteger(cantidad) && cantidad > 0) {
                const inicio = new Date(`${fecha.value}T12:00:00Z`);
                const fin = new Date(inicio);
                fin.setUTCDate(inicio.getUTCDate() + cantidad - 1);
                if (!Number.isNaN(fin.getTime()) && fin.getUTCFullYear() <= 9999) {
                    const formato = new Intl.DateTimeFormat('es-SV', { timeZone: 'UTC' });
                    resumen.textContent = `Del ${formato.format(inicio)} al ${formato.format(fin)}.`;
                }
            }
        }
        [opcion, fecha, dias].forEach(campo => campo.addEventListener('input', actualizar));
        actualizar();
    }
    document.querySelectorAll('[data-emitir]').forEach(boton => {
        boton.form.addEventListener('submit', () => { boton.disabled = true; boton.textContent = 'Guardando…'; });
    });
})();
