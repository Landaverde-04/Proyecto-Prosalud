from datetime import timedelta

from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone

from core.models import Clinica
from core.tests import PruebaCore
from seguridad.forms import permisos_asignables
from seguridad.models import Usuario
from .models import Lote, MovimientoInventario, Producto


class PruebaDeInventario(PruebaCore):
    """Montaje común: la administradora trabajando en ProSalud, que lleva inventario."""

    AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}

    def setUp(self):
        self.prosalud = Clinica.objects.create(nombre='ProSalud')
        self.estetica = Clinica.objects.create(nombre='Estética', tipo=Clinica.Tipo.ESTETICA)
        self.admin = self.usuario('admin', 'view_producto', 'add_producto', 'change_producto',
                                  'add_lote', 'view_movimientoinventario')
        self.client.force_login(self.admin)
        self.trabajar_en(self.prosalud)

    def usuario(self, nombre, *permisos):
        usuario = Usuario.objects.create_user(username=nombre, password='prueba', debe_cambiar_password=False)
        usuario.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='inventario', codename__in=permisos))
        usuario.clinicas.add(self.prosalud, self.estetica)
        return usuario

    def trabajar_en(self, clinica):
        self.client.post(reverse('core:cambiar_clinica'), {'clinica': clinica.pk})

    def producto(self, nombre, clinica=None, **datos):
        return Producto.objects.create(clinica=clinica or self.prosalud, nombre=nombre, **datos)

    def datos(self, **cambios):
        base = {'nombre': 'Suero fisiológico', 'presentacion': 'Bolsa 500 ml', 'unidad': 'bolsa',
                'se_usa_en_clinica': 'on', 'stock_minimo': '5', 'descripcion': ''}
        base.update(cambios)
        return {clave: valor for clave, valor in base.items() if valor is not None}


class ListaProductosTests(PruebaDeInventario):
    """INV-01: la lista del catálogo, con búsqueda y filtros."""

    url = reverse('inventario:lista_productos')

    def test_muestra_solo_los_productos_de_la_clinica(self):
        self.producto('Gasa estéril')
        self.producto('Crema hidratante', clinica=self.estetica)
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, 'Gasa estéril')
        self.assertNotContains(respuesta, 'Crema hidratante')

    def test_busca_por_nombre_o_presentacion(self):
        self.producto('Suero fisiológico', presentacion='Bolsa 500 ml')
        self.producto('Jeringa', presentacion='5 ml')
        respuesta = self.client.get(self.url, {'q': 'bolsa'}, **self.AJAX)
        self.assertContains(respuesta, 'Suero fisiológico')
        self.assertNotContains(respuesta, 'Jeringa')

    def test_la_busqueda_en_vivo_devuelve_solo_los_resultados(self):
        self.producto('Gasa estéril')
        respuesta = self.client.get(self.url, **self.AJAX)
        self.assertTemplateUsed(respuesta, 'inventario/resultados_productos.html')
        self.assertTemplateNotUsed(respuesta, 'inventario/lista_productos.html')

    def test_filtra_por_uso(self):
        self.producto('Gasa estéril', se_usa_en_clinica=True)
        self.producto('Protector solar', se_vende=True, se_usa_en_clinica=False)
        self.producto('Crema reparadora', se_vende=True, se_usa_en_clinica=True)
        venta = self.client.get(self.url, {'uso': 'venta'}, **self.AJAX)
        self.assertContains(venta, 'Protector solar')
        self.assertContains(venta, 'Crema reparadora')
        self.assertNotContains(venta, 'Gasa estéril')
        insumo = self.client.get(self.url, {'uso': 'insumo'}, **self.AJAX)
        self.assertContains(insumo, 'Gasa estéril')
        self.assertContains(insumo, 'Crema reparadora')
        self.assertNotContains(insumo, 'Protector solar')

    def test_por_defecto_oculta_los_inactivos(self):
        self.producto('Gasa estéril')
        self.producto('Algodón', activo=False)
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, 'Gasa estéril')
        self.assertNotContains(respuesta, 'Algodón')
        inactivos = self.client.get(self.url, {'estado': 'inactivos'}, **self.AJAX)
        self.assertContains(inactivos, 'Algodón')
        self.assertNotContains(inactivos, 'Gasa estéril')

    def test_en_la_clinica_estetica_no_hay_inventario(self):
        self.trabajar_en(self.estetica)
        respuesta = self.client.get(self.url)
        self.assertRedirects(respuesta, reverse('core:home'))

    def test_sin_permiso_no_entra(self):
        self.client.force_login(self.usuario('sin_permiso'))
        self.trabajar_en(self.prosalud)
        self.assertEqual(self.client.get(self.url).status_code, 403)


class MenuInventarioTests(PruebaDeInventario):
    """El apartado de Inventario en el menú: solo en la clínica médica y con permiso."""

    def test_aparece_en_la_clinica_medica(self):
        respuesta = self.client.get(reverse('core:home'))
        self.assertContains(respuesta, reverse('inventario:lista_productos'))

    def test_no_aparece_en_la_clinica_estetica(self):
        self.trabajar_en(self.estetica)
        respuesta = self.client.get(reverse('core:home'))
        self.assertNotContains(respuesta, reverse('inventario:lista_productos'))

    def test_no_aparece_sin_permiso(self):
        self.client.force_login(self.usuario('sin_permiso'))
        self.trabajar_en(self.prosalud)
        respuesta = self.client.get(reverse('core:home'))
        self.assertNotContains(respuesta, reverse('inventario:lista_productos'))


class RegistrarProductoTests(PruebaDeInventario):
    """INV-01: registrar y editar productos del catálogo."""

    url = reverse('inventario:crear_producto')

    def test_registra_el_producto_en_la_clinica_activa(self):
        respuesta = self.client.post(self.url, self.datos())
        self.assertRedirects(respuesta, reverse('inventario:lista_productos'))
        producto = Producto.objects.get()
        self.assertEqual(producto.clinica, self.prosalud)
        self.assertEqual(producto.unidad, Producto.Unidad.BOLSA)
        self.assertTrue(producto.se_usa_en_clinica)
        self.assertFalse(producto.se_vende)
        self.assertEqual(producto.stock_minimo, 5)
        self.assertEqual(producto.creado_por, self.admin)

    def test_puede_ser_de_venta_e_insumo_a_la_vez(self):
        self.client.post(self.url, self.datos(nombre='Crema reparadora', se_vende='on'))
        producto = Producto.objects.get()
        self.assertEqual(producto.usos, ['De venta', 'Insumo'])

    def test_pide_al_menos_un_uso(self):
        respuesta = self.client.post(self.url, self.datos(se_usa_en_clinica=None))
        self.assertContains(respuesta, 'Marca al menos un uso')
        self.assertFalse(Producto.objects.exists())

    def test_pide_el_nombre(self):
        respuesta = self.client.post(self.url, self.datos(nombre='   '))
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Producto.objects.exists())

    def test_no_acepta_existencia_minima_negativa(self):
        respuesta = self.client.post(self.url, self.datos(stock_minimo='-3'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Producto.objects.exists())

    def test_ordena_el_nombre_y_quita_espacios_de_sobra(self):
        self.client.post(self.url, self.datos(nombre='  suero   fisiológico ', presentacion=' bolsa  500 ml '))
        producto = Producto.objects.get()
        self.assertEqual(producto.nombre, 'Suero fisiológico')
        self.assertEqual(producto.presentacion, 'bolsa 500 ml')

    def test_no_repite_nombre_y_presentacion_en_la_clinica(self):
        self.producto('Suero fisiológico', presentacion='Bolsa 500 ml')
        respuesta = self.client.post(self.url, self.datos(nombre='SUERO FISIOLÓGICO', presentacion='bolsa 500 ml'))
        self.assertContains(respuesta, 'Ya existe un producto con ese nombre y esa presentación.')
        self.assertEqual(Producto.objects.count(), 1)

    def test_el_mismo_nombre_con_otra_presentacion_si_se_puede(self):
        self.producto('Suero fisiológico', presentacion='Bolsa 500 ml')
        self.client.post(self.url, self.datos(presentacion='Bolsa 1000 ml'))
        self.assertEqual(Producto.objects.count(), 2)

    def test_otra_clinica_puede_tener_el_mismo_producto(self):
        self.producto('Suero fisiológico', clinica=self.estetica, presentacion='Bolsa 500 ml')
        self.client.post(self.url, self.datos())
        self.assertEqual(Producto.objects.filter(clinica=self.prosalud).count(), 1)

    def test_rechaza_el_envio_si_cambio_de_clinica_en_otra_pestana(self):
        respuesta = self.client.post(self.url, self.datos(clinica_formulario=str(self.estetica.pk)))
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Producto.objects.exists())

    def test_quien_solo_ve_no_puede_registrar(self):
        self.client.force_login(self.usuario('enfermera', 'view_producto'))
        self.trabajar_en(self.prosalud)
        self.assertEqual(self.client.post(self.url, self.datos()).status_code, 403)
        self.assertFalse(Producto.objects.exists())

    def test_edita_el_producto(self):
        producto = self.producto('Suero fisiológico', presentacion='Bolsa 500 ml', stock_minimo=5)
        url = reverse('inventario:editar_producto', args=[producto.pk])
        self.assertContains(self.client.get(url), 'Bolsa 500 ml')
        self.client.post(url, self.datos(stock_minimo='10', se_vende='on'))
        producto.refresh_from_db()
        self.assertEqual(producto.stock_minimo, 10)
        self.assertTrue(producto.se_vende)
        self.assertEqual(producto.modificado_por, self.admin)

    def test_al_editar_no_choca_consigo_mismo(self):
        producto = self.producto('Suero fisiológico', presentacion='Bolsa 500 ml')
        url = reverse('inventario:editar_producto', args=[producto.pk])
        respuesta = self.client.post(url, self.datos(descripcion='Para hidratación'))
        self.assertRedirects(respuesta, reverse('inventario:lista_productos'))

    def test_no_edita_productos_de_otra_clinica(self):
        ajeno = self.producto('Crema', clinica=self.estetica)
        url = reverse('inventario:editar_producto', args=[ajeno.pk])
        self.assertEqual(self.client.get(url).status_code, 404)


class EstadoProductoTests(PruebaDeInventario):
    """Los productos no se eliminan: se desactivan y se pueden reactivar."""

    def test_desactiva_y_reactiva(self):
        producto = self.producto('Gasa estéril')
        url = reverse('inventario:cambiar_estado_producto', args=[producto.pk])
        self.client.post(url)
        producto.refresh_from_db()
        self.assertFalse(producto.activo)
        self.client.post(url)
        producto.refresh_from_db()
        self.assertTrue(producto.activo)
        self.assertEqual(Producto.objects.count(), 1)

    def test_solo_por_post(self):
        producto = self.producto('Gasa estéril')
        url = reverse('inventario:cambiar_estado_producto', args=[producto.pk])
        self.assertEqual(self.client.get(url).status_code, 405)


class PermisosInventarioTests(PruebaCore):
    """Los permisos del inventario se pueden asignar desde la pantalla de Roles."""

    def test_aparecen_en_los_permisos_asignables(self):
        codigos = set(permisos_asignables().filter(
            content_type__app_label='inventario').values_list('codename', flat=True))
        self.assertTrue({'view_producto', 'add_producto', 'change_producto', 'add_lote',
                         'view_movimientoinventario'} <= codigos)
        self.assertFalse(any(codigo.startswith('delete_') for codigo in codigos))


HOY = timezone.localdate()


class PruebaDeLotes(PruebaDeInventario):
    def lote(self, producto, cantidad, vence=None, actual=None, **datos):
        return Lote.objects.create(producto=producto, cantidad_inicial=cantidad,
                                   cantidad_actual=cantidad if actual is None else actual,
                                   fecha_vencimiento=vence, **datos)


class ExistenciaTests(PruebaDeLotes):
    """INV-02: la existencia suma los lotes que se pueden usar."""

    def test_suma_los_lotes_vigentes_y_los_que_no_vencen(self):
        suero = self.producto('Suero fisiológico')
        self.lote(suero, 10, vence=HOY + timedelta(days=200))
        self.lote(suero, 4)
        self.assertEqual(suero.calcular_existencia(), 14)
        self.assertEqual(Producto.objects.con_existencia().get().existencia, 14)

    def test_no_cuenta_lo_vencido_ni_lo_desactivado(self):
        suero = self.producto('Suero fisiológico')
        self.lote(suero, 10, vence=HOY - timedelta(days=1))
        self.lote(suero, 5, activo=False)
        self.lote(suero, 3, vence=HOY)
        self.assertEqual(suero.calcular_existencia(), 3)
        self.assertEqual(Producto.objects.con_existencia().get().existencia, 3)

    def test_sin_lotes_la_existencia_es_cero(self):
        self.producto('Gasa estéril')
        self.assertEqual(Producto.objects.con_existencia().get().existencia, 0)

    def test_existencia_baja_incluye_la_minima_y_la_vacia(self):
        normal = self.producto('Jeringa', stock_minimo=5)
        self.lote(normal, 6)
        en_el_minimo = self.producto('Gasa', stock_minimo=5)
        self.lote(en_el_minimo, 5)
        self.producto('Algodón', stock_minimo=0)
        bajos = set(Producto.objects.con_existencia_baja().values_list('nombre', flat=True))
        self.assertEqual(bajos, {'Gasa', 'Algodón'})

    def test_estado_del_lote(self):
        suero = self.producto('Suero')
        self.assertEqual(self.lote(suero, 1, vence=HOY + timedelta(days=90)).estado, 'vigente')
        self.assertEqual(self.lote(suero, 1, vence=HOY + timedelta(days=30)).estado, 'por_vencer')
        self.assertEqual(self.lote(suero, 1, vence=HOY - timedelta(days=1)).estado, 'vencido')
        self.assertEqual(self.lote(suero, 1, actual=0).estado, 'agotado')
        self.assertEqual(self.lote(suero, 1).estado, 'vigente')


class ExistenciaEnLaListaTests(PruebaDeLotes):
    url = reverse('inventario:lista_productos')

    def test_muestra_la_existencia_y_avisa_la_baja(self):
        suero = self.producto('Suero fisiológico', stock_minimo=5)
        self.lote(suero, 3)
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, 'title="Existencia baja (mínima: 5)"')
        self.assertContains(respuesta, '1 producto con existencia baja')

    def test_sin_existencia(self):
        self.producto('Gasa estéril')
        self.assertContains(self.client.get(self.url), 'title="Sin existencia"')

    def test_filtra_la_existencia_baja(self):
        suero = self.producto('Suero fisiológico', stock_minimo=5)
        self.lote(suero, 50)
        self.producto('Gasa estéril', stock_minimo=5)
        respuesta = self.client.get(self.url, {'existencia': 'baja'}, **self.AJAX)
        self.assertContains(respuesta, 'Gasa estéril')
        self.assertNotContains(respuesta, 'Suero fisiológico')

    def test_el_aviso_no_cuenta_los_inactivos(self):
        self.producto('Algodón', activo=False)
        self.assertNotContains(self.client.get(self.url), 'con existencia baja o sin existencia')

    def test_el_inicio_avisa_la_existencia_baja(self):
        self.producto('Gasa estéril', stock_minimo=5)
        self.assertContains(self.client.get(reverse('core:home')), '1 con existencia baja')


class DetalleProductoTests(PruebaDeLotes):
    def test_muestra_existencia_lotes_y_movimientos(self):
        suero = self.producto('Suero fisiológico', stock_minimo=2)
        lote = self.lote(suero, 10, vence=HOY + timedelta(days=10), numero_lote='L-77')
        MovimientoInventario.objects.create(lote=lote, tipo='entrada', cantidad=10, creado_por=self.admin)
        respuesta = self.client.get(reverse('inventario:detalle_producto', args=[suero.pk]))
        self.assertContains(respuesta, 'L-77')
        self.assertContains(respuesta, 'Vence en 10 días')
        self.assertContains(respuesta, '+10')
        self.assertEqual(respuesta.context['existencia'], 10)

    def test_quien_no_ve_movimientos_no_los_ve(self):
        suero = self.producto('Suero fisiológico')
        self.client.force_login(self.usuario('enfermera', 'view_producto'))
        self.trabajar_en(self.prosalud)
        respuesta = self.client.get(reverse('inventario:detalle_producto', args=[suero.pk]))
        self.assertIsNone(respuesta.context['movimientos'])
        self.assertNotContains(respuesta, 'Registrar entrada')

    def test_no_muestra_productos_de_otra_clinica(self):
        ajeno = self.producto('Crema', clinica=self.estetica)
        self.assertEqual(self.client.get(reverse('inventario:detalle_producto', args=[ajeno.pk])).status_code, 404)


class RegistrarEntradaTests(PruebaDeLotes):
    """INV-02: cada entrada crea un lote y deja su movimiento."""

    def setUp(self):
        super().setUp()
        self.suero = self.producto('Suero fisiológico', unidad='bolsa')
        self.url = reverse('inventario:registrar_entrada', args=[self.suero.pk])

    def datos(self, **cambios):
        base = {'cantidad_inicial': '20', 'numero_lote': ' L-2026  01 ',
                'fecha_vencimiento': (HOY + timedelta(days=365)).isoformat(),
                'fecha_entrada': HOY.isoformat(), 'referencia': 'Factura 123'}
        base.update(cambios)
        return {clave: valor for clave, valor in base.items() if valor is not None}

    def test_crea_el_lote_y_el_movimiento(self):
        respuesta = self.client.post(self.url, self.datos())
        self.assertRedirects(respuesta, reverse('inventario:detalle_producto', args=[self.suero.pk]))
        lote = Lote.objects.get()
        self.assertEqual((lote.cantidad_inicial, lote.cantidad_actual), (20, 20))
        self.assertEqual(lote.numero_lote, 'L-2026 01')
        self.assertEqual(lote.creado_por, self.admin)
        movimiento = MovimientoInventario.objects.get()
        self.assertEqual((movimiento.tipo, movimiento.cantidad), ('entrada', 20))
        self.assertEqual(movimiento.referencia, 'Factura 123')
        self.assertEqual(movimiento.creado_por, self.admin)
        self.assertEqual(self.suero.calcular_existencia(), 20)

    def test_sin_vencimiento_ni_numero_de_lote(self):
        self.client.post(self.url, self.datos(fecha_vencimiento='', numero_lote=''))
        lote = Lote.objects.get()
        self.assertIsNone(lote.fecha_vencimiento)
        self.assertEqual(lote.numero_lote, '')

    def test_la_fecha_de_entrada_viene_con_hoy(self):
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, f'value="{HOY.isoformat()}"')

    def test_pide_una_cantidad_de_al_menos_uno(self):
        for cantidad in ('0', '-5', ''):
            self.client.post(self.url, self.datos(cantidad_inicial=cantidad))
        self.assertFalse(Lote.objects.exists())
        self.assertFalse(MovimientoInventario.objects.exists())

    def test_no_acepta_un_lote_vencido(self):
        respuesta = self.client.post(self.url, self.datos(fecha_vencimiento=(HOY - timedelta(days=1)).isoformat()))
        self.assertContains(respuesta, 'Este lote ya está vencido')
        self.assertFalse(Lote.objects.exists())

    def test_no_acepta_una_fecha_de_entrada_futura(self):
        respuesta = self.client.post(self.url, self.datos(fecha_entrada=(HOY + timedelta(days=1)).isoformat()))
        self.assertContains(respuesta, 'La fecha de entrada no puede ser futura.')
        self.assertFalse(Lote.objects.exists())

    def test_no_da_entrada_a_un_producto_desactivado(self):
        self.suero.activo = False
        self.suero.save()
        self.client.post(self.url, self.datos())
        self.assertFalse(Lote.objects.exists())

    def test_sin_permiso_no_registra(self):
        self.client.force_login(self.usuario('enfermera', 'view_producto'))
        self.trabajar_en(self.prosalud)
        self.assertEqual(self.client.post(self.url, self.datos()).status_code, 403)
        self.assertFalse(Lote.objects.exists())

    def test_no_registra_en_productos_de_otra_clinica(self):
        ajeno = self.producto('Crema', clinica=self.estetica)
        url = reverse('inventario:registrar_entrada', args=[ajeno.pk])
        self.assertEqual(self.client.post(url, self.datos()).status_code, 404)
