from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db import transaction
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.clinica_activa import clinica_activa, formulario_de_otra_clinica
from core.paginacion import es_ajax, paginar

from .forms import EntradaForm, ProductoForm
from .models import MovimientoInventario, Producto

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

    productos = Producto.objects.filter(clinica=clinica).con_existencia()

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

    # Existencia baja: la minima o menos, incluidos los que no tienen nada.
    existencia = request.GET.get('existencia', '')
    if existencia == 'baja':
        productos = productos.filter(existencia__lte=F('stock_minimo'))

    total = productos.count()
    contexto = {
        'pagina': paginar(productos, request),
        'total': total,
        'consulta': consulta,
        'uso': uso,
        'estado': estado,
        'existencia': existencia,
        'hay_filtros': bool(consulta or uso or existencia or estado != 'activos'),
        # Aviso arriba de la lista: no cambia con la busqueda.
        'cuantos_bajos': Producto.objects.filter(clinica=clinica, activo=True).con_existencia_baja().count(),
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


@login_required
@permission_required('inventario.view_producto', raise_exception=True)
def detalle_producto(request, producto_id):
    """Datos del producto, su existencia y sus lotes, del que vence primero al ultimo (INV-02)."""
    clinica = clinica_con_inventario(request)
    if clinica is None:
        messages.info(request, MENSAJE_OTRA_CLINICA)
        return redirect('core:home')
    producto = producto_de_la_clinica(clinica, producto_id)
    existencia = producto.calcular_existencia()
    lotes = producto.lotes.filter(activo=True)
    movimientos = None
    if request.user.has_perm('inventario.view_movimientoinventario'):
        movimientos = (MovimientoInventario.objects.filter(lote__producto=producto)
                       .select_related('lote', 'creado_por')[:10])
    return render(request, 'inventario/detalle_producto.html', {
        'producto': producto,
        'existencia': existencia,
        'existencia_baja': existencia <= producto.stock_minimo,
        'lotes': lotes,
        'lotes_con_existencia': [lote for lote in lotes if lote.cantidad_actual > 0],
        'lotes_agotados': [lote for lote in lotes if lote.cantidad_actual == 0],
        'movimientos': movimientos,
    })


@login_required
@permission_required('inventario.add_lote', raise_exception=True)
def registrar_entrada(request, producto_id):
    """
    Entrada de un producto: crea el lote y deja el movimiento en el
    historial, las dos cosas juntas o ninguna.
    """
    clinica = clinica_con_inventario(request)
    if clinica is None:
        messages.info(request, MENSAJE_OTRA_CLINICA)
        return redirect('core:home')
    producto = producto_de_la_clinica(clinica, producto_id)
    if not producto.activo:
        messages.error(request, f'{producto} está desactivado: actívalo antes de darle entrada.')
        return redirect('inventario:detalle_producto', producto_id=producto.pk)

    form = EntradaForm(request.POST or None)
    if request.method == 'POST':
        if formulario_de_otra_clinica(request, clinica):
            messages.warning(
                request,
                f'Cambiaste de clínica en otra pestaña. Ahora trabajas en {clinica.nombre}: '
                'revisa los datos y vuelve a guardar.',
            )
        elif form.is_valid():
            with transaction.atomic():
                lote = form.save(commit=False)
                lote.producto = producto
                lote.cantidad_actual = lote.cantidad_inicial
                lote.creado_por = lote.modificado_por = request.user
                lote.save()
                MovimientoInventario.objects.create(
                    lote=lote, tipo=MovimientoInventario.Tipo.ENTRADA, cantidad=lote.cantidad_inicial,
                    referencia=lote.referencia, creado_por=request.user, modificado_por=request.user,
                )
            messages.success(request, f'Entrada registrada: {lote.cantidad_inicial} de {producto}.')
            return redirect('inventario:detalle_producto', producto_id=producto.pk)

    return render(request, 'inventario/form_entrada.html', {
        'form': form,
        'producto': producto,
        'existencia': producto.calcular_existencia(),
    })
