from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group, Permission
from django.db.models import Q
from django import forms

from core.models import Clinica

from .models import Usuario


# Apps del negocio: TODOS sus modelos aportan permisos automaticamente.
# Al crear una app nueva del negocio hay que agregarla aqui, o sus permisos
# nunca apareceran en el formulario de roles.
APPS_NEGOCIO = ['core', 'seguridad', 'pacientes', 'consultas']

# Excepcion puntual: "Roles" en la interfaz es el modelo Group de Django, que
# vive en la app 'auth'. Se incluye solo ese modelo y NO la app completa,
# porque ahi tambien vive Permission (el catalogo de permisos en si) y no
# queremos que nadie pueda editarlo desde una pantalla.
MODELOS_EXTRA = [('auth', 'group')]

# Regla del proyecto: nada se elimina, se desactiva. Los
# permisos delete_* no corresponden a ninguna accion real del sistema, asi
# que se ocultan para que nadie otorgue un permiso que no hace nada.
# Unica excepcion: los roles si se eliminan -- son configuracion, no datos
# clinicos, y borrarlos solo desasigna a sus usuarios.
MODELOS_ELIMINABLES = [('auth', 'group')]


def permisos_asignables():
    """
    Permisos que se pueden otorgar a un rol desde la interfaz.

    Unica fuente de verdad: la usan tanto el formulario (que valida lo que
    se guarda) como la vista (que dibuja las casillas). Si cada uno armara
    su propia consulta, podrian desincronizarse.
    """
    incluidos = Q(content_type__app_label__in=APPS_NEGOCIO)
    for app_label, modelo in MODELOS_EXTRA:
        incluidos |= Q(content_type__app_label=app_label, content_type__model=modelo)

    # Excluir delete_* salvo en los modelos donde eliminar si es una accion real
    borrados = Q(codename__startswith='delete_')
    for app_label, modelo in MODELOS_ELIMINABLES:
        borrados &= ~Q(content_type__app_label=app_label, content_type__model=modelo)

    return (
        Permission.objects
        .filter(incluidos)
        .exclude(borrados)
        .select_related('content_type')
        .order_by('content_type__app_label', 'codename')
    )


class RolForm(forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(
        queryset=permisos_asignables(),
        required=False,
        label='Permisos',
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Group
        fields = ('name', 'permissions')
        labels = {'name': 'Nombre del rol'}
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Vendedor, Administrador'}),
        }


class SelectRolUnico(forms.Select):
    """
    Desplegable de una sola opcion para un campo que por debajo es M2M.

    El Select normal de Django devuelve un valor suelto, pero 'groups' es una
    relacion de muchos a muchos y espera una lista. Esto hace de traductor.
    """

    def value_from_datadict(self, data, files, name):
        # getlist devuelve TODOS los valores enviados, no solo el ultimo. Asi
        # un POST armado a mano con dos roles llega completo a la validacion
        # y se rechaza, en vez de guardarse uno en silencio.
        if hasattr(data, 'getlist'):
            return [v for v in data.getlist(name) if v]
        valor = data.get(name)
        return [valor] if valor else []


class RolUnicoField(forms.ModelMultipleChoiceField):
    """
    Un usuario tiene UN rol.

    En la base sigue siendo una relacion de muchos a muchos (es el Group de
    Django, no lo tocamos), pero la interfaz solo deja elegir uno. Si alguien
    necesita una combinacion distinta de permisos, se crea un rol para eso.

    Se valida en el backend y no solo con el desplegable, porque un POST
    armado a mano podria mandar varios roles.
    """

    widget = SelectRolUnico

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('queryset', Group.objects.order_by('name'))
        kwargs.setdefault('required', False)
        kwargs.setdefault('label', 'Rol')
        super().__init__(*args, **kwargs)
        self.widget.attrs.setdefault('class', 'form-select')
        # ModelMultipleChoiceField fuerza empty_label=None; lo reponemos para
        # que el desplegable ofrezca la opcion de dejarlo sin rol
        self.empty_label = 'Sin rol'

    def clean(self, value):
        roles = super().clean(value)
        if len(roles) > 1:
            raise forms.ValidationError('Un usuario solo puede tener un rol.')
        return roles


def campo_clinicas():
    """
    A diferencia del rol, aqui SI se permite mas de una: la doctora
    administradora trabaja en las dos clinicas (Medica y Estetica), el
    resto del personal solo en la suya (TEC-01) -- por eso es un
    CheckboxSelectMultiple normal, sin el truco de RolUnicoField.
    """
    return forms.ModelMultipleChoiceField(
        queryset=Clinica.objects.order_by('nombre'),
        required=False,
        label='Clínicas',
        widget=forms.CheckboxSelectMultiple,
    )


class UsuarioCrearForm(UserCreationForm):
    groups = RolUnicoField()
    clinicas = campo_clinicas()

    class Meta:
        model = Usuario
        fields = ('username', 'first_name', 'last_name', 'email', 'is_active', 'groups', 'clinicas')
        labels = {
            'username': 'Nombre de usuario',
            'first_name': 'Nombre',
            'last_name': 'Apellido',
            'email': 'Correo electrónico',
            'is_active': 'Usuario activo',
        }


class ResetearPasswordForm(forms.Form):
    """
    Sin validate_password() a proposito (decision de Kevin, 10/09/2026,
    ver AUTH_PASSWORD_VALIDATORS en settings.py): esta contrasena es
    temporal -- Usuario.debe_cambiar_password obliga a cambiarla en el
    primer login -- asi que exigir que sea "dificil" aqui no protege
    nada real.
    """
    password1 = forms.CharField(label='Nueva contraseña', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirmar contraseña', widget=forms.PasswordInput)

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password1')
        p2 = cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Las contraseñas no coinciden.')
        return cleaned_data


class UsuarioEditarForm(forms.ModelForm):
    groups = RolUnicoField()
    clinicas = campo_clinicas()

    class Meta:
        model = Usuario
        fields = ('username', 'first_name', 'last_name', 'email', 'is_active', 'groups', 'clinicas')
        labels = {
            'username': 'Nombre de usuario',
            'first_name': 'Nombre',
            'last_name': 'Apellido',
            'email': 'Correo electrónico',
            'is_active': 'Usuario activo',
        }
