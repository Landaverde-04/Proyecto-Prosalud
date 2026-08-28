from django.shortcuts import redirect
from django.urls import reverse


class ForzarCambioPasswordMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and getattr(request.user, 'debe_cambiar_password', False)
        ):
            url_cambiar = reverse('seguridad:cambiar_password')
            url_logout = reverse('seguridad:logout')

            rutas_permitidas = {url_cambiar, url_logout}

            if (
                not request.path.startswith('/static/')
                and not request.path.startswith('/admin/')
                and request.path not in rutas_permitidas
            ):
                from django.contrib import messages
                messages.warning(
                    request,
                    'Tu administrador reseteó tu contraseña. '
                    'Por favor cambia a una nueva contraseña antes de continuar.'
                )
                return redirect(url_cambiar)

        return self.get_response(request)
