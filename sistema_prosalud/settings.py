from pathlib import Path
import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Leer variables de entorno desde .env
env = environ.Env()
environ.Env.read_env(BASE_DIR / '.env')

# Seguridad
SECRET_KEY = env('SECRET_KEY')
DEBUG = env.bool('DEBUG', default=False)
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.postgres',
    # Apps del proyecto
    'core',
    'seguridad',
    'pacientes',
    'consultas',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'seguridad.middleware.ForzarCambioPasswordMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'sistema_prosalud.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'sistema_prosalud.wsgi.application'


# Base de datos
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('DB_NAME'),
        'USER': env('DB_USER'),
        'PASSWORD': env('DB_PASSWORD'),
        'HOST': env('DB_HOST'),
        'PORT': env('DB_PORT', default='5432'),
    }
}


# Validacion de contrasenas: decision de Kevin (10/09/2026) -- sin
# validadores. La que pone el administrador al crear un usuario es
# temporal (Usuario.debe_cambiar_password la obliga a cambiarla en el
# primer login), asi que exigirle que sea "dificil" no protege nada; y
# la que pone despues cada quien para si misma es su eleccion -- si es
# corta o comun, la pantalla lo avisa (JS, sin bloquear), nunca lo
# rechaza. Antes tenia los 4 validadores por defecto de Django
# (similitud con el usuario, longitud minima, contrasena comun,
# solo numeros).
AUTH_PASSWORD_VALIDATORS = []


# Internacionalizacion
LANGUAGE_CODE = 'es'

TIME_ZONE = 'America/El_Salvador'

USE_I18N = True

USE_TZ = True


# Archivos estaticos
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# WhiteNoise: comprime (gzip) y agrega hash al nombre de cada archivo
# estatico para cache-busting automatico. Solo tiene efecto real cuando
# se corre 'collectstatic' (paso de build en produccion, no en runserver).
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# Modelo de usuario personalizado
AUTH_USER_MODEL = 'seguridad.Usuario'

# Autenticacion
LOGIN_URL = '/seguridad/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/seguridad/login/'

# Cierre de sesion por inactividad (pedido explicito de la clinica).
# SESSION_SAVE_EVERY_REQUEST es la pieza clave: sin ella, SESSION_COOKIE_AGE
# cuenta desde el login, no desde la ultima actividad. Con ella, cada
# request empuja el vencimiento hacia adelante -- solo expira si de verdad
# no hay actividad durante ese tiempo.
SESSION_COOKIE_AGE = 60 * 30  # 30 minutos de inactividad
SESSION_SAVE_EVERY_REQUEST = True

# Mapeo de etiquetas de mensajes a clases de Bootstrap
from django.contrib.messages import constants as messages_const
MESSAGE_TAGS = {
    messages_const.DEBUG: 'secondary',
    messages_const.INFO: 'info',
    messages_const.SUCCESS: 'success',
    messages_const.WARNING: 'warning',
    messages_const.ERROR: 'danger',
}
