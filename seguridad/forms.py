from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django import forms
from .models import Usuario


APPS_NEGOCIO = ['seguridad', 'inventario']


class RolForm(forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.filter(
            content_type__app_label__in=APPS_NEGOCIO
        ).select_related('content_type').order_by('content_type__app_label', 'codename'),
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


class UsuarioCrearForm(UserCreationForm):
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        required=False,
        label='Roles',
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Usuario
        fields = ('username', 'first_name', 'last_name', 'email', 'is_active', 'groups')
        labels = {
            'username': 'Nombre de usuario',
            'first_name': 'Nombre',
            'last_name': 'Apellido',
            'email': 'Correo electrónico',
            'is_active': 'Usuario activo',
        }


class ResetearPasswordForm(forms.Form):
    password1 = forms.CharField(label='Nueva contraseña', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirmar contraseña', widget=forms.PasswordInput)

    def clean_password1(self):
        password1 = self.cleaned_data.get('password1')
        validate_password(password1)
        return password1

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password1')
        p2 = cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Las contraseñas no coinciden.')
        return cleaned_data


class UsuarioEditarForm(forms.ModelForm):
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        required=False,
        label='Roles',
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Usuario
        fields = ('username', 'first_name', 'last_name', 'email', 'is_active', 'groups')
        labels = {
            'username': 'Nombre de usuario',
            'first_name': 'Nombre',
            'last_name': 'Apellido',
            'email': 'Correo electrónico',
            'is_active': 'Usuario activo',
        }
