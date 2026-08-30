from itertools import groupby

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView, PasswordChangeView
from django.contrib.auth.models import Group
from django.db.models import Count, Q
from django.contrib import messages
from django.urls import reverse_lazy

from core.auditoria import registrar
from core.models import RegistroAuditoria
from core.paginacion import paginar, es_ajax

from .models import Usuario
from .forms import UsuarioCrearForm, UsuarioEditarForm, RolForm, ResetearPasswordForm, permisos_asignables


_ACCIONES_ES = {
    'add': 'Agregar',
    'change': 'Modificar',
    'delete': 'Eliminar',
    'view': 'Ver',
}

# El app_label y el nombre del modelo son tecnicos ('auth', 'group'); en la
# pantalla de roles se muestran con el nombre que usa la clinica.
_APPS_ES = {
    'auth': 'Roles',
    'core': 'Auditoría',
    'seguridad': 'Usuarios',
    'pacientes': 'Pacientes',
    'consultas': 'Consultas',
}

_MODELOS_ES = {
    'group': 'rol',
    'usuario': 'usuario',
    'registroauditoria': 'bitácora de auditoría',
}


# --- Guarda del último administrador ---
#
# Quien puede editar roles y sus permisos puede reconstruir cualquier acceso
# del sistema, incluido el propio. Si nadie queda con esa facultad, el sistema
# se tranca y solo se recupera desde la consola del servidor. Por eso las
# vistas de abajo bloquean cualquier accion que dejaria cero administradores.

PERMISO_ADMINISTRACION = 'auth.change_group'


def _grupos_administran(grupos):
    """¿Alguno de estos roles otorga la administración de roles?"""
    pks = [g.pk for g in grupos] if grupos else []
    if not pks:
        return False
    return Group.objects.filter(
        pk__in=pks,
        permissions__codename='change_group',
        permissions__content_type__app_label='auth',
    ).exists()


def _seguiria_administrando(usuario, grupos, activo=True):
    """¿El usuario podría seguir administrando roles con estos datos?"""
    return bool(activo) and (usuario.is_superuser or _grupos_administran(grupos))


def _hay_otro_administrador(excluir_usuario=None, excluir_rol=None):
    """
    ¿Queda algún usuario activo capaz de administrar roles, sin contar al
    usuario (o sin contar el rol) que está por cambiar?

    Solo mira superusuarios y roles, que es como se otorgan los permisos en
    este sistema. No contempla permisos asignados directo a un usuario porque
    no hay ninguna pantalla que los otorgue.
    """
    usuarios = Usuario.objects.filter(is_active=True)
    if excluir_usuario is not None:
        usuarios = usuarios.exclude(pk=excluir_usuario.pk)

    for u in usuarios.prefetch_related('groups'):
        if u.is_superuser:
            return True
        grupos = list(u.groups.all())
        if excluir_rol is not None:
            grupos = [g for g in grupos if g.pk != excluir_rol.pk]
        if _grupos_administran(grupos):
            return True
    return False


def _etiqueta_permiso(permiso):
    """
    Traduce un permiso tecnico ('change_group') a texto que la clinica
    entienda ('Modificar rol'). Unica fuente de verdad: la usan tanto el
    formulario de roles como el detalle que se guarda en la bitacora de
    auditoria, para que nunca se le muestre un codename crudo a nadie.
    """
    accion = permiso.codename.split('_')[0]
    modelo = _MODELOS_ES.get(permiso.content_type.model, permiso.content_type.model)
    return f"{_ACCIONES_ES.get(accion, accion)} {modelo}"


def _permisos_agrupados():
    permisos = permisos_asignables()
    resultado = []
    for app_label, grupo in groupby(permisos, key=lambda p: p.content_type.app_label):
        items = [{'pk': p.pk, 'label': _etiqueta_permiso(p)} for p in grupo]
        resultado.append((_APPS_ES.get(app_label, app_label), items))
    return resultado


@login_required
@permission_required('seguridad.view_usuario', raise_exception=True)
def lista_usuarios(request):
    usuarios = Usuario.objects.prefetch_related('groups').order_by('username')

    consulta = request.GET.get('q', '').strip()
    if consulta:
        usuarios = usuarios.filter(
            Q(username__icontains=consulta)
            | Q(first_name__icontains=consulta)
            | Q(last_name__icontains=consulta)
        )

    total = usuarios.count()
    pagina = paginar(usuarios, request)

    contexto = {'pagina': pagina, 'consulta': consulta, 'total': total}
    plantilla = 'seguridad/resultados_usuarios.html' if es_ajax(request) else 'seguridad/lista_usuarios.html'
    return render(request, plantilla, contexto)


@login_required
@permission_required('seguridad.view_usuario', raise_exception=True)
def detalle_usuario(request, id):
    usuario = get_object_or_404(Usuario, pk=id)
    return render(request, 'seguridad/detalle_usuario.html', {'usuario': usuario})


@login_required
@permission_required('seguridad.add_usuario', raise_exception=True)
def crear_usuario(request):
    if request.method == 'POST':
        form = UsuarioCrearForm(request.POST)
        if form.is_valid():
            usuario = form.save(commit=False)
            usuario.debe_cambiar_password = True
            usuario.save()
            form.save_m2m()
            rol = usuario.groups.first()
            registrar(
                request,
                RegistroAuditoria.Accion.CREAR_USUARIO,
                objetivo=usuario.username,
                detalle=f'Rol asignado: {rol.name}' if rol else 'Sin rol',
            )
            messages.success(request, 'Usuario creado correctamente.')
            return redirect('seguridad:lista_usuarios')
    else:
        form = UsuarioCrearForm()
    return render(request, 'seguridad/form_usuario.html', {'form': form, 'accion': 'Crear'})


@login_required
@permission_required('seguridad.change_usuario', raise_exception=True)
def editar_usuario(request, id):
    usuario = get_object_or_404(Usuario, pk=id)

    # Se consulta ANTES de armar el formulario: al validar, el ModelForm ya
    # escribe los valores nuevos sobre la instancia y has_perm() devolveria
    # el estado propuesto en vez del actual.
    era_administrador = usuario.has_perm(PERMISO_ADMINISTRACION)
    rol_anterior = usuario.groups.first()
    estaba_activo = usuario.is_active

    if request.method == 'POST':
        form = UsuarioEditarForm(request.POST, instance=usuario)
        if form.is_valid():
            seguira = _seguiria_administrando(
                usuario,
                form.cleaned_data.get('groups'),
                activo=form.cleaned_data.get('is_active'),
            )
            if era_administrador and not seguira and not _hay_otro_administrador(excluir_usuario=usuario):
                form.add_error(
                    None,
                    f'{usuario.username} es el único usuario que puede administrar roles. '
                    'Dale ese rol a alguien más antes de quitárselo o desactivarlo, '
                    'o nadie podrá administrar el sistema.'
                )
            else:
                form.save()

                cambios = []
                rol_nuevo = usuario.groups.first()
                if rol_anterior != rol_nuevo:
                    cambios.append(
                        f'Rol: {rol_anterior.name if rol_anterior else "sin rol"} '
                        f'→ {rol_nuevo.name if rol_nuevo else "sin rol"}'
                    )
                if estaba_activo != usuario.is_active:
                    cambios.append('Activado' if usuario.is_active else 'Desactivado')

                registrar(
                    request,
                    RegistroAuditoria.Accion.EDITAR_USUARIO,
                    objetivo=usuario.username,
                    detalle=' · '.join(cambios),
                )
                messages.success(request, 'Usuario actualizado correctamente.')
                return redirect('seguridad:lista_usuarios')
    else:
        form = UsuarioEditarForm(instance=usuario)
    return render(request, 'seguridad/form_usuario.html', {'form': form, 'accion': 'Editar', 'usuario': usuario})


@login_required
@permission_required('seguridad.change_usuario', raise_exception=True)
def cambiar_estado_usuario(request, id):
    """
    Activa o desactiva un usuario. Regla del proyecto: los usuarios NO se
    eliminan. Borrarlos ademas arrastraria los registros clinicos que los
    referencian como doctor que atendio.
    """
    usuario = get_object_or_404(Usuario, pk=id)

    if request.method != 'POST':
        return redirect('seguridad:detalle_usuario', id=id)

    # Sin esto, un administrador puede dejarse fuera del sistema el mismo
    if usuario == request.user:
        messages.error(request, 'No puedes desactivar tu propia cuenta.')
        return redirect('seguridad:detalle_usuario', id=id)

    if (
        usuario.is_active
        and usuario.has_perm(PERMISO_ADMINISTRACION)
        and not _hay_otro_administrador(excluir_usuario=usuario)
    ):
        messages.error(
            request,
            f'No puedes desactivar a {usuario.username}: es el único usuario que '
            'puede administrar roles. Asigna ese rol a alguien más primero.'
        )
        return redirect('seguridad:detalle_usuario', id=id)

    usuario.is_active = not usuario.is_active
    usuario.save(update_fields=['is_active'])

    registrar(
        request,
        RegistroAuditoria.Accion.ACTIVAR_USUARIO if usuario.is_active
        else RegistroAuditoria.Accion.DESACTIVAR_USUARIO,
        objetivo=usuario.username,
    )

    if usuario.is_active:
        messages.success(request, f'Usuario {usuario.username} activado correctamente.')
    else:
        messages.success(request, f'Usuario {usuario.username} desactivado. Ya no podrá iniciar sesión.')

    return redirect('seguridad:lista_usuarios')


# --- Roles ---

@login_required
@permission_required('auth.view_group', raise_exception=True)
def lista_roles(request):
    # distinct=True en ambos: sin el, combinar dos Count() de relaciones
    # M2M distintas en la misma consulta infla los totales (join cruzado).
    roles = Group.objects.annotate(
        total_usuarios=Count('user', distinct=True),
        total_permisos=Count('permissions', distinct=True),
    ).order_by('name')

    consulta = request.GET.get('q', '').strip()
    if consulta:
        roles = roles.filter(name__icontains=consulta)

    total = roles.count()
    pagina = paginar(roles, request)

    contexto = {'pagina': pagina, 'consulta': consulta, 'total': total}
    plantilla = 'seguridad/resultados_roles.html' if es_ajax(request) else 'seguridad/lista_roles.html'
    return render(request, plantilla, contexto)


@login_required
@permission_required('auth.add_group', raise_exception=True)
def crear_rol(request):
    if request.method == 'POST':
        form = RolForm(request.POST)
        if form.is_valid():
            rol = form.save()
            registrar(
                request,
                RegistroAuditoria.Accion.CREAR_ROL,
                objetivo=rol.name,
                detalle=f'{rol.permissions.count()} permisos asignados',
            )
            messages.success(request, 'Rol creado correctamente.')
            return redirect('seguridad:lista_roles')
        permisos_seleccionados = set(int(pk) for pk in request.POST.getlist('permissions') if pk)
    else:
        form = RolForm()
        permisos_seleccionados = set()
    return render(request, 'seguridad/form_rol.html', {
        'form': form,
        'accion': 'Crear',
        'permisos_agrupados': _permisos_agrupados(),
        'permisos_seleccionados': permisos_seleccionados,
    })


@login_required
@permission_required('auth.change_group', raise_exception=True)
def editar_rol(request, id):
    rol = get_object_or_404(Group, pk=id)
    if request.method == 'POST':
        # Se capturan antes de guardar: cambiar los permisos de un rol es de
        # lo mas delicado que se puede hacer, y la bitacora debe decir
        # exactamente que se agrego y que se quito, no solo "lo editaron".
        nombre_anterior = rol.name
        permisos_antes = {
            p.codename: p for p in rol.permissions.select_related('content_type')
        }

        form = RolForm(request.POST, instance=rol)
        if form.is_valid():
            form.save()

            permisos_despues = {
                p.codename: p for p in rol.permissions.select_related('content_type')
            }
            cambios = []
            if nombre_anterior != rol.name:
                cambios.append(f'Nombre: {nombre_anterior} → {rol.name}')
            if agregados := sorted(permisos_despues.keys() - permisos_antes.keys()):
                etiquetas = sorted(_etiqueta_permiso(permisos_despues[c]) for c in agregados)
                cambios.append('Agregó: ' + ', '.join(etiquetas))
            if quitados := sorted(permisos_antes.keys() - permisos_despues.keys()):
                etiquetas = sorted(_etiqueta_permiso(permisos_antes[c]) for c in quitados)
                cambios.append('Quitó: ' + ', '.join(etiquetas))

            registrar(
                request,
                RegistroAuditoria.Accion.EDITAR_ROL,
                objetivo=rol.name,
                detalle=' · '.join(cambios) or 'Sin cambios',
            )
            messages.success(request, 'Rol actualizado correctamente.')
            return redirect('seguridad:lista_roles')
        permisos_seleccionados = set(int(pk) for pk in request.POST.getlist('permissions') if pk)
    else:
        form = RolForm(instance=rol)
        permisos_seleccionados = set(rol.permissions.values_list('pk', flat=True))
    return render(request, 'seguridad/form_rol.html', {
        'form': form,
        'accion': 'Editar',
        'rol': rol,
        'permisos_agrupados': _permisos_agrupados(),
        'permisos_seleccionados': permisos_seleccionados,
    })


@login_required
@permission_required('auth.delete_group', raise_exception=True)
def eliminar_rol(request, id):
    rol = get_object_or_404(Group, pk=id)
    if request.method == 'POST':
        if _grupos_administran([rol]) and not _hay_otro_administrador(excluir_rol=rol):
            messages.error(
                request,
                f'No puedes eliminar el rol "{rol.name}": es el único que permite '
                'administrar roles. Si lo borras, nadie podrá administrar el sistema.'
            )
            return redirect('seguridad:lista_roles')
        total_usuarios = rol.user_set.count()
        nombre = rol.name
        rol.delete()
        registrar(
            request,
            RegistroAuditoria.Accion.ELIMINAR_ROL,
            objetivo=nombre,
            detalle=f'{total_usuarios} usuario(s) quedaron desvinculados' if total_usuarios else '',
        )
        messages.success(request, 'Rol eliminado correctamente.')
        return redirect('seguridad:lista_roles')
    return render(request, 'seguridad/eliminar_rol.html', {'rol': rol})


@login_required
@permission_required('auth.change_group', raise_exception=True)
def usuarios_rol(request, id):
    rol = get_object_or_404(Group, pk=id)
    if request.method == 'POST':
        accion = request.POST.get('accion')
        usuario_id = request.POST.get('usuario_id')
        usuario = get_object_or_404(Usuario, pk=usuario_id)
        era_administrador = usuario.has_perm(PERMISO_ADMINISTRACION)
        rol_anterior = usuario.groups.exclude(pk=rol.pk).first()

        if accion == 'agregar':
            # Un usuario tiene un solo rol, asi que asignar este reemplaza al
            # que tuviera antes (ver RolUnicoField en forms.py)
            grupos_nuevos = [rol]
        elif accion == 'quitar':
            grupos_nuevos = [g for g in usuario.groups.all() if g.pk != rol.pk]
        else:
            return redirect('seguridad:usuarios_rol', id=id)

        if (
            era_administrador
            and not _seguiria_administrando(usuario, grupos_nuevos, activo=usuario.is_active)
            and not _hay_otro_administrador(excluir_usuario=usuario)
        ):
            messages.error(
                request,
                f'{usuario.username} es el único usuario que puede administrar roles. '
                'Dale ese rol a alguien más antes de quitárselo.'
            )
            return redirect('seguridad:usuarios_rol', id=id)

        usuario.groups.set(grupos_nuevos)

        if accion == 'agregar':
            detalle = (
                f'{rol_anterior.name} → {rol.name}' if rol_anterior
                else f'Sin rol → {rol.name}'
            )
        else:
            detalle = f'{rol.name} → sin rol'
        registrar(
            request,
            RegistroAuditoria.Accion.CAMBIAR_ROL,
            objetivo=usuario.username,
            detalle=detalle,
        )

        if accion == 'agregar' and rol_anterior:
            messages.success(
                request,
                f'{usuario.username} pasó del rol "{rol_anterior.name}" a "{rol.name}".'
            )
        elif accion == 'agregar':
            messages.success(request, f'Usuario {usuario.username} agregado al rol.')
        else:
            messages.success(request, f'Usuario {usuario.username} quitado del rol.')

        return redirect('seguridad:usuarios_rol', id=id)

    usuarios_con_rol = rol.user_set.all().order_by('username')
    usuarios_sin_rol = Usuario.objects.exclude(groups=rol).order_by('username')
    return render(request, 'seguridad/usuarios_rol.html', {
        'rol': rol,
        'usuarios_con_rol': usuarios_con_rol,
        'usuarios_sin_rol': usuarios_sin_rol,
    })


# --- Inicio y cierre de sesion ---

# Django no distingue "la sesion vencio" de "nunca inicio sesion": en ambos
# casos simplemente no hay sesion. Por eso al entrar se deja esta cookie,
# que sobrevive a la sesion. Si al llegar al login la marca existe pero ya
# no hay sesion, es que vencio por inactividad y se puede avisar.
COOKIE_SESION_PREVIA = 'prosalud_sesion_previa'
DIAS_MARCA_SESION = 30


class IniciarSesionView(LoginView):
    template_name = 'seguridad/login.html'

    def get(self, request, *args, **kwargs):
        respuesta = super().get(request, *args, **kwargs)

        vencio = (
            request.COOKIES.get(COOKIE_SESION_PREVIA)
            and not request.user.is_authenticated
        )
        if vencio:
            messages.warning(
                request,
                'Tu sesión se cerró por inactividad. '
                'Vuelve a iniciar sesión para continuar.'
            )
            # Se borra la marca para no repetir el aviso en cada recarga
            respuesta.delete_cookie(COOKIE_SESION_PREVIA)

        return respuesta

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        respuesta.set_cookie(
            COOKIE_SESION_PREVIA,
            '1',
            max_age=60 * 60 * 24 * DIAS_MARCA_SESION,
            httponly=True,
            samesite='Lax',
        )
        return respuesta


class CerrarSesionView(LogoutView):
    """Salir a proposito no es un vencimiento: se borra la marca."""

    def dispatch(self, request, *args, **kwargs):
        respuesta = super().dispatch(request, *args, **kwargs)
        respuesta.delete_cookie(COOKIE_SESION_PREVIA)
        return respuesta


# --- Reseteo de contraseña por administrador ---

@login_required
@permission_required('seguridad.change_usuario', raise_exception=True)
def resetear_password(request, id):
    usuario = get_object_or_404(Usuario, pk=id)
    if request.method == 'POST':
        form = ResetearPasswordForm(request.POST)
        if form.is_valid():
            usuario.set_password(form.cleaned_data['password1'])
            usuario.debe_cambiar_password = True
            usuario.save()
            registrar(
                request,
                RegistroAuditoria.Accion.RESETEAR_PASSWORD,
                objetivo=usuario.username,
            )
            messages.success(
                request,
                f'Contraseña de {usuario.username} restablecida. '
                'El usuario deberá cambiarla en su próximo acceso.'
            )
            return redirect('seguridad:detalle_usuario', id=id)
    else:
        form = ResetearPasswordForm()
    return render(request, 'seguridad/resetear_password.html', {'form': form, 'usuario': usuario})


# --- Perfil propio ---

@login_required
def mi_perfil(request):
    return render(request, 'seguridad/mi_perfil.html')


class CambiarPasswordView(LoginRequiredMixin, PasswordChangeView):
    template_name = 'seguridad/cambiar_password.html'
    success_url = reverse_lazy('seguridad:mi_perfil')

    def form_valid(self, form):
        self.request.user.debe_cambiar_password = False
        self.request.user.save(update_fields=['debe_cambiar_password'])
        messages.success(self.request, 'Contraseña actualizada correctamente.')
        return super().form_valid(form)
