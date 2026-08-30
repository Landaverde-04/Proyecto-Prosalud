/*
 * Vista previa visual del modulo de Pacientes -- sin modelo Paciente
 * todavia (HU-25 pendiente). Los "pacientes" de aqui viven solo en el
 * localStorage de este navegador: sirven para demostrar el flujo
 * (listar, registrar, ver expediente) antes de tener base de datos
 * real. No es persistencia de verdad ni se comparte entre usuarios.
 */
(function () {
    var CLAVE = 'prosalud_pacientes_demo';
    var CLAVE_VERSION = 'prosalud_pacientes_demo_version';
    // Subir este numero cuando cambie semilla() para que se
    // vuelva a sembrar sola (pisa pacientes agregados a mano).
    var VERSION_SEMILLA = 2;

    function semilla() {
        return [
            {
                id: 'demo-1',
                tipo: 'adulto',
                nombres: 'Maria Elena',
                apellidos: 'Hernandez Perez',
                dui: '04521678-9',
                telefono: '7845-1122',
                fechaNacimiento: '1988-03-14',
                contacto: { nombre: 'Carlos Hernandez', parentesco: 'Esposo', telefono: '7845-1123' }
            },
            {
                id: 'demo-2',
                tipo: 'menor',
                nombres: 'Santiago',
                apellidos: 'Martinez Lopez',
                dui: '',
                telefono: '',
                fechaNacimiento: '2019-07-02',
                responsable: { nombre: 'Ana Lopez', parentesco: 'Madre', telefono: '7011-9988', dui: '03344556-1' }
            },
            {
                id: 'demo-3',
                tipo: 'adulto',
                nombres: 'Jose Roberto',
                apellidos: 'Munoz Castro',
                dui: '06678123-4',
                telefono: '7233-4455',
                fechaNacimiento: '1975-11-30',
                contacto: { nombre: 'Gloria Castro', parentesco: 'Hermana', telefono: '7233-4456' }
            },
            {
                id: 'demo-4',
                tipo: 'adulto',
                nombres: 'Ana Beatriz',
                apellidos: 'Flores Alvarado',
                dui: '05123456-7',
                telefono: '7011-2233',
                fechaNacimiento: '1990-01-22',
                contacto: { nombre: 'Marta Alvarado', parentesco: 'Madre', telefono: '7011-2234' }
            },
            {
                id: 'demo-5',
                tipo: 'adulto',
                nombres: 'Carlos Alberto',
                apellidos: 'Rivera Torres',
                dui: '',
                telefono: '7899-3344',
                fechaNacimiento: '1965-06-10',
                contacto: { nombre: 'Elena Torres', parentesco: 'Esposa', telefono: '7899-3345' }
            },
            {
                id: 'demo-6',
                tipo: 'menor',
                nombres: 'Sofia Nicole',
                apellidos: 'Escobar Cruz',
                dui: '',
                telefono: '',
                fechaNacimiento: '2015-09-05',
                responsable: { nombre: 'Patricia Cruz', parentesco: 'Madre', telefono: '7456-6677', dui: '04455667-8' }
            },
            {
                id: 'demo-7',
                tipo: 'adulto',
                nombres: 'Miguel Angel',
                apellidos: 'Guevara Mejia',
                dui: '03987654-2',
                telefono: '7788-9900',
                fechaNacimiento: '1955-12-01',
                contacto: { nombre: 'Rosa Mejia', parentesco: 'Hermana', telefono: '7788-9901' }
            },
            {
                id: 'demo-8',
                tipo: 'adulto',
                nombres: 'Daniela Abigail',
                apellidos: 'Portillo Reyes',
                dui: '',
                telefono: '7654-3210',
                fechaNacimiento: '2002-04-18',
                contacto: { nombre: 'Juan Portillo', parentesco: 'Padre', telefono: '7654-3211' }
            },
            {
                id: 'demo-9',
                tipo: 'menor',
                nombres: 'Diego Alejandro',
                apellidos: 'Romero Salazar',
                dui: '',
                telefono: '',
                fechaNacimiento: '2011-02-27',
                responsable: { nombre: 'Carmen Salazar', parentesco: 'Madre', telefono: '7321-9988', dui: '' }
            },
            {
                id: 'demo-10',
                tipo: 'adulto',
                nombres: 'Fatima Esperanza',
                apellidos: 'Vasquez Zelaya',
                dui: '06112233-4',
                telefono: '7900-1122',
                fechaNacimiento: '1998-08-30',
                contacto: { nombre: 'Oscar Vasquez', parentesco: 'Hermano', telefono: '7900-1123' }
            },
            {
                id: 'demo-11',
                tipo: 'adulto',
                nombres: 'Rodrigo Ernesto',
                apellidos: 'Zelaya Ramirez',
                dui: '',
                telefono: '7233-5566',
                fechaNacimiento: '1982-10-14',
                contacto: { nombre: 'Lucia Ramirez', parentesco: 'Esposa', telefono: '7233-5567' }
            },
            {
                id: 'demo-12',
                tipo: 'menor',
                nombres: 'Camila Sofia',
                apellidos: 'Reyes Lopez',
                dui: '',
                telefono: '',
                fechaNacimiento: '2021-12-19',
                responsable: { nombre: 'Marlene Lopez', parentesco: 'Madre', telefono: '7677-8899', dui: '05566778-1' }
            },
            {
                id: 'demo-13',
                tipo: 'adulto',
                nombres: 'Oscar Ivan',
                apellidos: 'Salazar Gonzalez',
                dui: '04223344-5',
                telefono: '7345-6677',
                fechaNacimiento: '1970-05-08',
                contacto: { nombre: 'Beatriz Gonzalez', parentesco: 'Esposa', telefono: '7345-6678' }
            },
            {
                id: 'demo-14',
                tipo: 'adulto',
                nombres: 'Gabriela Isabel',
                apellidos: 'Torres Martinez',
                dui: '',
                telefono: '7011-4455',
                fechaNacimiento: '1993-07-25',
                contacto: { nombre: 'Ricardo Martinez', parentesco: 'Esposo', telefono: '7011-4456' }
            },
            {
                id: 'demo-15',
                tipo: 'menor',
                nombres: 'Andres Felipe',
                apellidos: 'Cruz Hernandez',
                dui: '',
                telefono: '',
                fechaNacimiento: '2017-03-11',
                responsable: { nombre: 'Silvia Hernandez', parentesco: 'Madre', telefono: '7899-2233', dui: '' }
            },
            {
                id: 'demo-16',
                tipo: 'adulto',
                nombres: 'Valentina Lucia',
                apellidos: 'Mejia Rivera',
                dui: '05887766-3',
                telefono: '7456-1122',
                fechaNacimiento: '1960-09-19',
                contacto: { nombre: 'Manuel Rivera', parentesco: 'Esposo', telefono: '7456-1123' }
            },
            {
                id: 'demo-17',
                tipo: 'adulto',
                nombres: 'Emilio Jose',
                apellidos: 'Portillo Flores',
                dui: '',
                telefono: '7788-3344',
                fechaNacimiento: '1985-11-02',
                contacto: { nombre: 'Karla Flores', parentesco: 'Esposa', telefono: '7788-3345' }
            },
            {
                id: 'demo-18',
                tipo: 'menor',
                nombres: 'Isabella Renata',
                apellidos: 'Guevara Torres',
                dui: '',
                telefono: '',
                fechaNacimiento: '2013-06-23',
                responsable: { nombre: 'Diana Torres', parentesco: 'Madre', telefono: '7900-5566', dui: '06778899-2' }
            }
        ];
    }

    function obtenerPacientes() {
        var versionGuardada = parseInt(localStorage.getItem(CLAVE_VERSION) || '0', 10);
        var datos = localStorage.getItem(CLAVE);
        if (!datos || versionGuardada < VERSION_SEMILLA) {
            var iniciales = semilla();
            localStorage.setItem(CLAVE, JSON.stringify(iniciales));
            localStorage.setItem(CLAVE_VERSION, String(VERSION_SEMILLA));
            return iniciales;
        }
        try {
            return JSON.parse(datos);
        } catch (e) {
            return semilla();
        }
    }

    function guardarPacientes(lista) {
        localStorage.setItem(CLAVE, JSON.stringify(lista));
    }

    function agregarPaciente(paciente) {
        var lista = obtenerPacientes();
        paciente.id = 'demo-' + Date.now();
        lista.unshift(paciente);
        guardarPacientes(lista);
        return paciente;
    }

    function buscarPorId(id) {
        var lista = obtenerPacientes();
        for (var i = 0; i < lista.length; i++) {
            if (lista[i].id === id) return lista[i];
        }
        return null;
    }

    function calcularEdad(fechaNacimiento) {
        if (!fechaNacimiento) return null;
        var hoy = new Date();
        var nacimiento = new Date(fechaNacimiento + 'T00:00:00');
        var edad = hoy.getFullYear() - nacimiento.getFullYear();
        var mes = hoy.getMonth() - nacimiento.getMonth();
        if (mes < 0 || (mes === 0 && hoy.getDate() < nacimiento.getDate())) edad--;
        return edad;
    }

    function nombreCompleto(paciente) {
        return (paciente.nombres + ' ' + paciente.apellidos).trim();
    }

    // Aviso flotante (estilo toast) para las tarjetas del expediente
    // que todavia no tienen pantalla real detras.
    function mostrarAviso(texto) {
        var contenedor = document.getElementById('avisos-flotantes');
        if (!contenedor) {
            contenedor = document.createElement('div');
            contenedor.id = 'avisos-flotantes';
            contenedor.className = 'toast-container position-fixed bottom-0 end-0 p-3';
            contenedor.style.zIndex = 1080;
            document.body.appendChild(contenedor);
        }
        var toastEl = document.createElement('div');
        toastEl.className = 'toast align-items-center text-white border-0';
        toastEl.style.backgroundColor = 'var(--accent)';
        toastEl.setAttribute('role', 'status');
        toastEl.innerHTML =
            '<div class="d-flex">' +
            '<div class="toast-body d-flex align-items-center gap-2">' +
            '<i class="bi bi-info-circle"></i> ' + texto +
            '</div>' +
            '<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>' +
            '</div>';
        contenedor.appendChild(toastEl);
        var toast = new bootstrap.Toast(toastEl, { delay: 2500 });
        toast.show();
        toastEl.addEventListener('hidden.bs.toast', function () {
            toastEl.remove();
        });
    }

    window.PacientesDemo = {
        obtenerPacientes: obtenerPacientes,
        agregarPaciente: agregarPaciente,
        buscarPorId: buscarPorId,
        calcularEdad: calcularEdad,
        nombreCompleto: nombreCompleto,
        mostrarAviso: mostrarAviso
    };
})();
