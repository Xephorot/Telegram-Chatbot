# Chatbot de Ventas con Django y Botpress

Este proyecto implementa un backend de Django para un chatbot de ventas y servicio al cliente. El backend expone una API REST que puede ser consumida por una plataforma de chatbot como **Botpress**.

## Arquitectura

- **Backend (Este proyecto)**: Django + Django REST Framework, proporciona la API para gestionar datos.
- **Base de Datos**: PostgreSQL (Docker).
- **Chatbot Builder**: **Botpress**. Aquí se construye el flujo de la conversación y se gestiona la lógica del bot. Botpress se conecta a los canales (ej. Telegram) y consume la API de Django para obtener datos.
- **IA**: La lógica de IA (NLU/NLP) se maneja dentro de Botpress, que puede ser mejorado con modelos como los de OpenAI o Gemini.

## Características del Backend

- 🔐 Panel de administración para gestionar productos, pedidos, usuarios, etc.
- 🌐 API REST completa para interactuar con los datos.
- 🛒 Modelos de datos para productos, categorías, usuarios, conversaciones y pedidos.

## Tecnologías Utilizadas

- **Backend**: Django + Django REST Framework
- **Base de Datos**: PostgreSQL (Docker)
- **Chatbot Framework**: Botpress (se configura por separado)

## Requisitos Previos

- Python 3.8+
- Docker y Docker Compose
- Una cuenta de **Botpress Cloud** (gratuita para empezar)
- Una cuenta de Telegram

## Instalación del Backend

### 1. Clonar el repositorio

```bash
git clone <url-del-repositorio>
cd <directorio-del-proyecto>
```

### 2. Configurar el entorno virtual

El script de setup se encarga de esto.

### 3. Configurar variables de entorno

Copia el archivo `.env-example` a `.env` y edita los valores:

```bash
cp .env-example .env
```

Edita el archivo `.env` con una `SECRET_KEY` segura.

### 4. Ejecutar el script de configuración

En sistemas Unix/Linux/MacOS:
```bash
chmod +x setup.sh
./setup.sh
```

En Windows (PowerShell):
```powershell
.\setup.ps1
```
*Nota: Este script te preguntará si deseas crear un superusuario para el panel de administración.*

## Uso del Backend

### Iniciar el servidor de desarrollo

```bash
python manage.py runserver
```
El servidor Django se ejecutará en `http://localhost:8000`.

### Acceso al panel de administración

1. Visita http://localhost:8000/admin/
2. Inicia sesión con las credenciales del superusuario creado durante la instalación.
3. **¡Importante!** Añade algunas `Categorías` y `Productos` para que el bot tenga datos que mostrar.

## Despliegue en Producción

El proyecto está configurado para ser desplegado en dos plataformas complementarias:

### 1. Despliegue Backend Django en Render

El backend principal de Django (directorio raíz, `chatbot_project`, `telegram_bot`) se despliega en Render para manejar la API REST y administración.

#### Preparación para Render

1. Crea una cuenta en [Render](https://render.com/) si aún no tienes una.
2. Conecta tu cuenta de GitHub con Render.
3. Configura un nuevo servicio Web:
   - Selecciona tu repositorio.
   - Nombre: `chatbot-backend-django`
   - Tipo: Web Service
   - Runtime: Python
   - Build Command: `./build.sh`
   - Start Command: `gunicorn chatbot_project.wsgi:application`

#### Configuración del archivo render.yaml

El proyecto ya incluye un archivo `render.yaml` que automatiza la configuración:

```yaml
databases:
  - name: chatbot-postgres-db
    plan: free
    databaseName: chatbot_db
    user: chatbot_user

services:
  - type: web
    name: chatbot-backend-django
    plan: free
    runtime: python
    buildCommand: "./build.sh"
    startCommand: "gunicorn chatbot_project.wsgi:application"
```

#### Variables de Entorno en Render

Debes configurar manualmente las siguientes variables de entorno en el dashboard de Render:

- `DEBUG`: False
- `SECRET_KEY`: Genera una clave secreta única
- `DJANGO_SUPERUSER_USERNAME`: admin_render (o el que prefieras)
- `DJANGO_SUPERUSER_EMAIL`: tu@email.com
- `DJANGO_SUPERUSER_PASSWORD`: Una contraseña segura (configúrala como "Secret")
- `GEMINI_API_KEY`: Tu clave API de Google Gemini (configúrala como "Secret")
- `TELEGRAM_BOT_TOKEN`: Token de tu bot de Telegram (configúrala como "Secret")

### 2. Despliegue del Bot de Telegram en Railway

El servicio del bot de Telegram (directorio `bot_service`) se despliega por separado en Railway para mayor estabilidad y escalabilidad.

#### Preparación para Railway

1. Crea una cuenta en [Railway](https://railway.app/) si aún no tienes una.
2. Conecta tu cuenta de GitHub con Railway.
3. Crea un nuevo proyecto:
   - Selecciona "Deploy from GitHub repository"
   - Selecciona tu repositorio
   - En la configuración del servicio, cambia el directorio raíz a `bot_service`
   - Define el comando de inicio: `python main.py`

#### Variables de Entorno en Railway

Debes configurar las siguientes variables de entorno en Railway:

- `TELEGRAM_BOT_TOKEN`: El token de tu bot de Telegram (obtenido de BotFather)
- `GEMINI_API_KEY`: Tu clave API de Google Gemini
- `API_BASE_URL`: La URL de tu backend en Render (por ejemplo: https://chatbot-backend-django.onrender.com)

#### Configuración del Procfile

El directorio `bot_service` ya incluye un `Procfile` que Railway utilizará para iniciar el servicio:

```
web: python main.py
```

## Configuración Clave: API_BASE_URL

La variable de entorno `API_BASE_URL` es crucial para conectar ambas partes del sistema:

1. En desarrollo local, `API_BASE_URL` apunta a `http://localhost:8000`
2. En producción, `API_BASE_URL` debe configurarse en Railway para apuntar a tu URL de Render (ej. `https://chatbot-backend-django.onrender.com`).

## Flujo de Despliegue Recomendado

1. **Primero despliega el backend en Render**:
   - Asegúrate de que la base de datos se crea correctamente.
   - Verifica que la API esté funcionando visitando `https://tu-app-render.onrender.com/api/products/`.
   - Accede al panel de administración y añade algunos productos y categorías.

2. **Luego despliega el bot en Railway**:
   - Configura la variable `API_BASE_URL` para que apunte a tu URL de Render.
   - Despliega el bot y verifica que inicie correctamente.
   - Prueba tu bot en Telegram para asegurarte de que puede acceder a los datos del backend.

## Solución de Problemas de Despliegue

### Problemas en Render
- Verifica los logs del servicio en el dashboard de Render.
- Asegúrate de que el script `build.sh` tiene permisos de ejecución (`git update-index --chmod=+x build.sh`).
- Si hay problemas con la base de datos, revisa la configuración de la URL de conexión.

### Problemas en Railway
- Verifica los logs del servicio en el dashboard de Railway.
- Comprueba que las variables de entorno están correctamente configuradas.
- Asegúrate de que el bot puede acceder a la API (prueba la URL de `API_BASE_URL` manualmente).

## Configuración de Botpress

### 1. Crear una cuenta en Botpress

- Ve a [Botpress Cloud](https://botpress.com/) y crea una cuenta gratuita.
- Crea un nuevo chatbot.

### 2. Conectar con Telegram

- Dentro de tu bot en Botpress, ve a la sección de **Integrations**.
- Selecciona **Telegram** y sigue las instrucciones. Necesitarás el token de tu bot de Telegram que obtienes de **BotFather**.

### 3. Conectar Botpress con tu Backend Desplegado

Configura las acciones en Botpress para utilizar tu API desplegada en Render:

- **Ejemplo: Obtener lista de productos**
  - En un nodo de tu flujo, añade una tarjeta **HTTP Request**.
  - **URL:** `https://tu-app-render.onrender.com/api/products/`
  - **Method:** `GET`
  - Guarda la respuesta en una variable de Botpress (ej. `variable.products`).
  - Usa la información de la variable para mostrar los productos al usuario.

## API REST

La API REST del backend está disponible en las siguientes rutas (usando tu URL de Render):

- `/api/products/`: Lista de productos
- `/api/categories/`: Categorías de productos
- `/api/conversations/`: Conversaciones registradas
- `/api/orders/`: Pedidos realizados
- `/api/faqs/`: Preguntas frecuentes

## Licencia

Este proyecto está licenciado bajo [MIT License](LICENSE). 