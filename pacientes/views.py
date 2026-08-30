from django.contrib.auth.decorators import login_required
from django.shortcuts import render

# Vista previa visual del modulo de Pacientes: sin modelo Paciente
# todavia (HU-25 pendiente), asi que estas vistas solo renderizan la
# plantilla y el dato de ejemplo vive en el navegador (localStorage),
# via pacientes-mock.js. Por eso no llevan @permission_required -- no
# existe un permiso real que proteger todavia. Cuando se implemente el
# modelo de verdad, esto se reemplaza por vistas con datos reales y la
# doble proteccion de decoradores que usa el resto del sistema.


@login_required
def lista_pacientes(request):
    return render(request, 'pacientes/lista_pacientes.html')


@login_required
def nuevo_paciente(request):
    return render(request, 'pacientes/nuevo_paciente.html')


@login_required
def ver_paciente(request, id):
    return render(request, 'pacientes/ver_paciente.html', {'paciente_id': id})
