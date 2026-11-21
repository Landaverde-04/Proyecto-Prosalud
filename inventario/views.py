from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.clinica_activa import clinica_activa, formulario_de_otra_clinica
from core.paginacion import es_ajax, paginar

from .forms import ProductoForm
from .models import Producto

MENSAJE_OTRA_CLINICA = 'El inventario solo está disponible en la clínica médica.'


def clinica_con_inventario(request):
    """La clinica activa, si lleva inventario. None si no (la estetica o sin clinica)."""
    clinica = clinica_activa(request)
    return clinica if clinica and clinica.usa_inventario else None


def producto_de_la_clinica(clinica, producto_id):
    return get_object_or_404(Producto, pk=producto_id, clinica=clinica)


@login_required
@permission_required('inventario.view_producto', raise_exception=True)
def lista_productos(request):
    clinica = clinica_con_inventario(request)
    if clinica is None:
        messages.info(request, MENSAJE_OTRA_CLINICA)
        return redirect('core:home')

    productos = Producto.objects.filter(clinica=clinica)

    consulta = request.GET.get('q', '').strip()
    if consulta:
        productos = productos.filter(
            Q(nombre__icontains=consulta)
            | Q(presentacion__icontains=consulta)
            | Q(descripcion__icontains=consulta)
        )

    uso = request.GET.get('uso', '')
    if uso == 'venta':
        productos = productos.filter(se_vende=True)
    elif uso == 'insumo':
        productos = productos.filter(se_usa_en_clinica=True)

    # Por defecto solo los activos: los desactivados se consultan aparte.
    estado = request.GET.get('estado', 'activos')
    if estado == 'activos':
        productos = productos.filter(activo=True)
    elif estado == 'inactivos':
        productos = productos.filter(activo=False)

    total = productos.count()
    contexto = {
        'pagina': paginar(productos, request),
        'total': total,
        'consulta': consulta,
        'uso': uso,
        'estado': estado,
        'hay_filtros': bool(consulta or uso or estado != 'activos'),
    }
    plantilla = 'inventario/resultados_productos.html' if es_ajax(request) else 'inventario/lista_productos.html'
    return render(request, plantilla, contexto)


def guardar_producto(request, clinica, producto=None):
    """Alta y edicion comparten todo menos el mensaje final."""
    form = ProductoForm(request.POST or None, instance=producto, clinica=clinica)
    if request.method == 'POST':
        if formulario_de_otra_clinica(request, clinica):
            messages.warning(
                request,
                f'Cambiaste de clínica en otra pestaña. Ahora trabajas en {clinica.nombre}: '
                'revisa los datos y vuelve a guardar.',
            )
        elif form.is_valid():
            nuevo = form.save(commit=False)
            if producto is None:
                nuevo.clinica = clinica
                nuevo.creado_por = request.user
            nuevo.modificado_por = request.user
            nuevo.save()
            messages.success(
                request, f'Producto {"actualizado" if producto else "registrado"}: {nuevo}.')
            return redirect('inventario:lista_productos')

    return render(request, 'inventario/form_producto.html', {
        'form': form,
        'producto': producto,
        'accion': 'Editar' if producto else 'Nuevo',
    })


@login_required
@permission_required('inventario.add_producto', raise_exception=True)
def crear_producto(request):
    clinica = clinica_con_inventario(request)
    if clinica is None:
        messages.info(request, MENSAJE_OTRA_CLINICA)
        return redirect('core:home')
    return guardar_producto(request, clinica)


@login_required
@permission_required('inventario.change_producto', raise_exception=True)
def editar_producto(request, producto_id):
    clinica = clinica_con_inventario(request)
    if clinica is None:
        messages.info(request, MENSAJE_OTRA_CLINICA)
        return redirect('core:home')
    return guardar_producto(request, clinica, producto_de_la_clinica(clinica, producto_id))


@require_POST
@login_required
@permission_required('inventario.change_producto', raise_exception=True)
def cambiar_estado_producto(request, producto_id):
    """Los productos no se eliminan: se desactivan, como todo en el sistema."""
    clinica = clinica_con_inventario(request)
    if clinica is None:
        messages.info(request, MENSAJE_OTRA_CLINICA)
        return redirect('core:home')
    producto = producto_de_la_clinica(clinica, producto_id)
    producto.activo = not producto.activo
    producto.modificado_por = request.user
    producto.save(update_fields=['activo', 'modificado_por', 'fecha_modificacion'])
    messages.success(
        request, f'Producto {"activado" if producto.activo else "desactivado"}: {producto}.')
    return redirect('inventario:lista_productos')
