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

# ── Seguridad detras del proxy (produccion) ──────────────────────────
# Todo esto se enciende con una sola variable, para que en desarrollo no
# cambie nada: sin HTTPS local, forzar cookies seguras dejaria fuera al
# navegador y nadie podria iniciar sesion.
DETRAS_DE_PROXY_HTTPS = env.bool('DETRAS_DE_PROXY_HTTPS', default=False)

if DETRAS_DE_PROXY_HTTPS:
    # La pieza clave, y la que Django no avisa que falta: el proxy termina
    # el HTTPS y a la aplicacion le llega una peticion HTTP normal con esta
    # cabecera. Sin esto request.is_secure() es falso, la comprobacion de
    # origen de CSRF no cuadra y TODOS los formularios fallan, login incluido.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    # Quien entre por http:// sube a https:// en vez de quedarse sin cifrar.
    SECURE_SSL_REDIRECT = True
    # La sesion y el token CSRF solo viajan por conexiones cifradas.
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # El navegador recuerda por un año que este sitio es solo HTTPS, asi la
    # primera visita del dia tampoco pasa por http.
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    # Origenes en los que Django confia para formularios; con https explicito,
    # que es lo que exige Django desde la version 4.
    CSRF_TRUSTED_ORIGINS = [f'https://{host}' for host in ALLOWED_HOSTS if host != '*']


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
                'core.context_processors.clinica_activa',
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

# ── Almacenamiento de adjuntos clínicos en Cloudflare R2 ─────────────
# Nombre del bucket de R2; si no está en el .env queda vacío
R2_BUCKET = env('R2_BUCKET', default='')

# Solo si hay bucket configurado se usa R2; si no, sigue el disco local
if R2_BUCKET:
    # La app de django-storages se registra solo aquí, no siempre:
    # así, sin variables de R2, Django arranca aunque la librería no
    # esté instalada (desarrollo local y pruebas)
    INSTALLED_APPS.append('storages')
    # Reemplaza el almacenamiento por defecto (el que usan los FileField)
    STORAGES['default'] = {
        # Backend S3 de django-storages; R2 habla el mismo idioma que S3
        'BACKEND': 'storages.backends.s3.S3Storage',
        'OPTIONS': {
            # Bucket privado donde viven los adjuntos
            'bucket_name': R2_BUCKET,
            # Dirección de la cuenta de Cloudflare, armada con el Account ID
            'endpoint_url': f"https://{env('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
            # Llave pública del token de R2 (solo lectura/escritura de este bucket)
            'access_key': env('R2_ACCESS_KEY_ID'),
            # Llave secreta del mismo token; nunca se escribe en el código
            'secret_key': env('R2_SECRET_ACCESS_KEY'),
            # R2 no tiene regiones como AWS; 'auto' es lo que pide Cloudflare
            'region_name': 'auto',
            # Firma moderna de peticiones, la única que acepta R2
            'signature_version': 's3v4',
            # R2 no usa permisos por archivo: la privacidad la da el bucket
            'default_acl': None,
            # Si alguien llamara a .url, la dirección sale firmada y no pública
            'querystring_auth': True,
            # Y esa firma vence a los 5 minutos
            'querystring_expire': 300,
            # Nunca sobrescribir un archivo existente con el mismo nombre
            'file_overwrite': False,
        },
    }

# Archivos que sube la gente: los adjuntos del expediente (HU-EXP-08).
#
# NO se define MEDIA_URL a proposito. Definirla invita a escribir
# `{{ adjunto.archivo.url }}` en una plantilla, y eso deja el archivo
# clinico colgando de una direccion que cualquiera puede abrir con solo
# tenerla. Los adjuntos se descargan por una vista con login, permisos y
# validacion de clinica -- ver `consultas.views.descargar_adjunto`.
#
# La carpeta va FUERA del repositorio (`BASE_DIR.parent`) para que ningun
# expediente termine en un commit por accidente.
#
# Pendiente: la historia contempla mover esto a S3 con bucket privado y
# URL firmada temporal. Cuando se haga, solo cambia el backend de
# almacenamiento; la vista protegida y sus permisos se quedan igual.
MEDIA_ROOT = BASE_DIR.parent / 'archivos-prosalud'

# Tope por archivo, del criterio de HU-EXP-08. Se valida en el formulario;
# aqui solo se nombra una vez para no repetir el numero.
TAMANO_MAXIMO_ADJUNTO = 10 * 1024 * 1024  # 10 MB

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
