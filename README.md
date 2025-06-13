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

## Configuración de Botpress

### 1. Crear una cuenta en Botpress

- Ve a [Botpress Cloud](https://botpress.com/) y crea una cuenta gratuita.
- Crea un nuevo chatbot.

### 2. Conectar con Telegram

- Dentro de tu bot en Botpress, ve a la sección de **Integrations**.
- Selecciona **Telegram** y sigue las instrucciones. Necesitarás el token de tu bot de Telegram que obtienes de **BotFather**.

### 3. Conectar Botpress con tu Backend Local

Botpress Cloud necesita acceder a tu API de Django, pero tu servidor local no es accesible desde internet. Para solucionar esto, puedes usar **ngrok**.

- **Instala ngrok:** Sigue las instrucciones en [ngrok.com](https://ngrok.com/download).
- **Expón tu puerto local:** Abre una nueva terminal (sin cerrar la de Django) y ejecuta:
  ```bash
  ngrok http 8000
  ```
- `ngrok` te dará una URL pública (`https://<hash-aleatorio>.ngrok-free.app`). Esta URL redirige el tráfico a tu `localhost:8000`. **Usa esta URL en Botpress**.

### 4. Crear Acciones en Botpress

Dentro del flujo de tu bot en Botpress, para obtener datos de tu API, usarás la tarjeta **"Execute Code"** o harás llamadas **HTTP Request**.

- **Ejemplo: Obtener lista de productos**
  - En un nodo de tu flujo, añade una tarjeta **HTTP Request**.
  - **URL:** `https://<tu-url-de-ngrok>.ngrok-free.app/api/products/`
  - **Method:** `GET`
  - Guarda la respuesta en una variable de Botpress (ej. `variable.products`).
  - Usa la información de la variable para mostrar los productos al usuario.

## API REST

La API REST del backend está disponible en las siguientes rutas (usando tu URL de ngrok):

- `/api/products/`: Lista de productos
- `/api/categories/`: Categorías de productos
- `/api/conversations/`: Conversaciones registradas
- `/api/orders/`: Pedidos realizados
- `/api/faqs/`: Preguntas frecuentes

## Licencia

Este proyecto está licenciado bajo [MIT License](LICENSE). 