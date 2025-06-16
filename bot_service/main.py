import logging
import os
import requests
import google.generativeai as genai

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    Defaults,
)

# --- Configuración de Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Variables de Entorno (se configurarán en Railway) ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
API_BASE_URL = os.environ.get("API_BASE_URL")  # La URL de tu API en Render

# --- Configuración de APIs ---
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    GEMINI_MODEL = genai.GenerativeModel("gemini-1.5-flash")
else:
    GEMINI_MODEL = None
    logger.warning("GEMINI_API_KEY no encontrada. Las funciones de IA estarán deshabilitadas.")

# --- Funciones de Ayuda (interactúan con la API de Render) ---

def get_products_from_api(limit: int = 50) -> str:
    """Obtiene la lista de productos desde la API de Render."""
    if not API_BASE_URL:
        return "Error: La URL de la API no está configurada."
    try:
        response = requests.get(f"{API_BASE_URL}/api/products/?limit={limit}")
        response.raise_for_status()
        
        data = response.json()
        # La API de Django REST Framework con paginación devuelve los datos en la clave 'results'
        products = data.get('results', [])
        
        if not products:
            return "Actualmente no tenemos productos disponibles en el catálogo. ¡Vuelve pronto!"
            
        lines = [f"📦 ID: {p['id']} - {p['name']} - ${p['price']} (Stock: {p['stock']})" for p in products]
        return "\n".join(lines)
    except requests.RequestException as e:
        logger.error(f"Error al contactar la API de productos: {e}")
        return "⚙️ Lo siento, no pude conectarme con el sistema de productos en este momento."

def get_faqs_from_api(only_questions: bool = False) -> str:
    """
    Obtiene la lista de FAQs desde la API de Render.
    Si only_questions es True, devuelve solo la lista de preguntas.
    """
    if not API_BASE_URL:
        return "Error: La URL de la API no está configurada."
    try:
        # Usamos un límite alto para traer todas las FAQs, asumiendo que no serán miles.
        response = requests.get(f"{API_BASE_URL}/api/faqs/?limit=100")
        response.raise_for_status()
        
        data = response.json()
        faqs = data.get('results', [])
        
        if not faqs:
            return "" # Retorna vacío si no hay FAQs

        if only_questions:
            lines = [f"❓ {faq['question']}" for faq in faqs]
        else:
            lines = [f"- Pregunta: {faq['question']}\n  Respuesta: {faq['answer']}" for faq in faqs]
            
        return "\n".join(lines)
    except requests.RequestException as e:
        logger.error(f"Error al contactar la API de FAQs: {e}")
        return "" # Retorna vacío en caso de error

async def log_conversation(user: dict, user_text: str, bot_text: str):
    """Guarda la conversación completa (usuario, conversación, mensajes) en la API."""
    if not API_BASE_URL:
        logger.error("No se puede registrar la conversación: API_BASE_URL no está configurada.")
        return

    # 1. Obtener o crear el usuario
    user_id = None
    try:
        # Primero intenta obtener el usuario por telegram_id
        response = requests.get(f"{API_BASE_URL}/api/users/?telegram_id={user.id}")
        response.raise_for_status()
        results = response.json().get('results', [])
        
        if results:
            user_id = results[0]['id']
        else:
            # Si no existe, créalo
            user_payload = {
                "telegram_id": str(user.id),
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
            }
            response = requests.post(f"{API_BASE_URL}/api/users/", json=user_payload)
            response.raise_for_status()
            user_id = response.json()['id']
    except requests.RequestException as e:
        logger.error(f"Error al obtener/crear usuario en la API: {e}")
        return

    if not user_id:
        logger.error("No se pudo obtener un user_id para registrar la conversación.")
        return

    # 2. Crear una nueva entrada de conversación
    conv_id = None
    try:
        conv_payload = {"user": user_id}
        response = requests.post(f"{API_BASE_URL}/api/conversations/", json=conv_payload)
        response.raise_for_status()
        conv_id = response.json()['id']
    except requests.RequestException as e:
        logger.error(f"Error al crear la conversación en la API: {e}")
        return

    if not conv_id:
        logger.error("No se pudo obtener un conv_id para registrar los mensajes.")
        return

    # 3. Registrar ambos mensajes
    try:
        # Mensaje del usuario
        msg_user_payload = {"conversation": conv_id, "sender": "user", "content": user_text}
        requests.post(f"{API_BASE_URL}/api/messages/", json=msg_user_payload).raise_for_status()
        
        # Mensaje del bot
        msg_bot_payload = {"conversation": conv_id, "sender": "bot", "content": bot_text}
        requests.post(f"{API_BASE_URL}/api/messages/", json=msg_bot_payload).raise_for_status()
        
        logger.info(f"Conversación {conv_id} registrada con éxito.")
    except requests.RequestException as e:
        logger.error(f"Error al registrar mensajes en la API: {e}")

# --- Handlers de Telegram ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para el comando /start."""
    user = update.effective_user
    welcome_text = (
        f"¡Hola {user.first_name}! 👋 Soy tu asistente de compras virtual.\n\n"
        "Puedo ayudarte con lo siguiente:\n"
        "✅ `/productos` - Ver todos nuestros artículos.\n"
        "✅ `/reservar <ID> <cantidad>` - Asegura un producto.\n"
        "✅ `/ayuda` - Resuelve tus dudas sobre nosotros.\n\n"
        "También puedes escribirme lo que necesites y usaré mi IA para ayudarte."
    )
    
    # Simplemente envía el mensaje de bienvenida, sin procesarlo con la IA.
    await update.message.reply_text(welcome_text)
    logger.info(f"Usuario {user.username} ({user.id}) inició una conversación con /start.")
    # No es necesario registrar este mensaje inicial como una "conversación" de IA.

async def productos_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para el comando /productos."""
    product_list = get_products_from_api()
    await update.message.reply_text(product_list)

async def ayuda_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Maneja el comando de ayuda.
    - Si se usa solo `/ayuda`, muestra la lista de FAQs.
    - Si se usa `/ayuda <pregunta>`, intenta responderla usando la IA.
    """
    user_question = " ".join(context.args)
    
    # Caso 1: El usuario solo escribe /ayuda para ver las opciones
    if not user_question:
        faq_questions = get_faqs_from_api(only_questions=True)
        if not faq_questions:
            response_text = "Actualmente no tenemos una sección de preguntas frecuentes, pero puedes consultarme lo que necesites."
        else:
            response_text = (
                "Aquí tienes las preguntas más frecuentes. ¡Espero que te sirvan! 👍\n\n"
                f"{faq_questions}\n\n"
                "Puedes escribirme una de estas preguntas o cualquier otra duda que tengas."
            )
        await update.message.reply_text(response_text)
        return

    # Caso 2: El usuario hace una pregunta específica con /ayuda
    faqs_context = get_faqs_from_api(only_questions=False) # Obtenemos Q&A
    prompt = (
        "Eres un asistente de soporte al cliente muy amable. Tu única fuente de verdad es la siguiente lista de Preguntas y Respuestas (FAQs). "
        "Tu tarea es responder a la pregunta del usuario basándote únicamente en este contexto. Sé conciso y directo.\n\n"
        "--- INICIO CONTEXTO FAQs ---\n"
        f"{faqs_context}\n"
        "--- FIN CONTEXTO FAQs ---\n\n"
        f"Pregunta del usuario: \"{user_question}\"\n\n"
        "Si la respuesta está en el contexto, respóndela amablemente. "
        "Si la respuesta NO está en el contexto, di: 'Lo siento, no tengo información sobre eso. Aquí tienes otras preguntas que quizás te ayuden:' y lista 3 preguntas del contexto que más se parezcan a la del usuario."
    )

    bot_response_text = ""
    try:
        response = GEMINI_MODEL.generate_content(prompt)
        bot_response_text = response.text
        await update.message.reply_text(bot_response_text)
    except Exception as e:
        logger.error(f"Error en la API de Gemini (ayuda): {e}")
        bot_response_text = "⚙️ Tuve un problema al procesar tu consulta. Por favor, intenta más tarde."
        await update.message.reply_text(bot_response_text)

    # Registrar la interacción de ayuda
    await log_conversation(
        user=update.effective_user,
        user_text=f"/ayuda {user_question}",
        bot_text=bot_response_text
    )

async def recomendar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usa Gemini para recomendar productos basándose en la lista de la API."""
    if not GEMINI_MODEL:
        await update.message.reply_text("Lo siento, la función de recomendación no está disponible ahora mismo.")
        return
        
    product_list = get_products_from_api(limit=100)
    prompt = (
        "Eres un asistente de ventas experto y muy conciso. Basado en la siguiente lista de productos, "
        "recomienda los 3 mejores artículos para un cliente. "
        "Usa un salto de línea para separar cada recomendación. No uses negritas, asteriscos ni otro formato especial. Sé breve.\n\n"
        f"Lista de productos:\n{product_list}"
    )
    
    bot_response_text = ""
    try:
        response = GEMINI_MODEL.generate_content(prompt)
        bot_response_text = response.text
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text=bot_response_text
        )
    except Exception as e:
        logger.error(f"Error en la API de Gemini: {e}")
        bot_response_text = "⚙️ Tuve un problema al generar la recomendación. Por favor, intenta de nuevo."
        await update.message.reply_text(bot_response_text)
    
    # Registrar conversación
    await log_conversation(
        user=update.effective_user,
        user_text=update.message.text,
        bot_text=bot_response_text
    )

async def reservar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para el comando /reservar."""
    if not API_BASE_URL:
        await update.message.reply_text("Error: La función de reserva no está configurada.")
        return
        
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("⚠️ **Uso incorrecto:**\n`/reservar <ID_del_producto> <cantidad>`\n\n*Ejemplo:* `/reservar 15 2`")
        return

    try:
        product_id = int(args[0])
        quantity = int(args[1])
    except ValueError:
        await update.message.reply_text("Por favor, asegúrate de que el ID y la cantidad sean números.")
        return

    user = update.effective_user
    payload = {
        "telegram_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "quantity": quantity
    }

    try:
        response = requests.post(f"{API_BASE_URL}/api/products/{product_id}/reserve/", json=payload)
        response.raise_for_status()
        
        order_data = response.json()
        total = float(order_data['total_amount'])
        await update.message.reply_text(
            f"¡Reserva exitosa! ✅\nTu pedido (ID: {order_data['id']}) ha sido actualizado.\n"
            f"El nuevo total es: **${total:.2f}**"
        )
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            await update.message.reply_text("❌ No se encontró un producto con ese ID.")
        elif e.response.status_code == 400:
            error_detail = e.response.json().get('error', 'petición inválida.')
            await update.message.reply_text(f"❌ Error en la reserva: {error_detail}")
        else:
            logger.error(f"Error HTTP no manejado al reservar: {e}")
            await update.message.reply_text("Ocurrió un error inesperado al procesar tu reserva.")
    except requests.RequestException as e:
        logger.error(f"Error de conexión al reservar: {e}")
        await update.message.reply_text("No pude conectarme al sistema de pedidos. Inténtalo más tarde.")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja cualquier mensaje de texto que no sea un comando."""
    if not GEMINI_MODEL:
        await update.message.reply_text("Lo siento, la función de IA no está disponible ahora mismo.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    
    user_text = update.message.text
    logger.info(f"Usuario '{update.effective_user.username}' envió un mensaje de texto para procesar con IA.")

    # Obtener contextos
    faqs_context = get_faqs_from_api(only_questions=False)
    products_context = get_products_from_api(limit=100)

    # Prompt mejorado y más específico
    prompt = (
        "Eres un asistente de ventas y soporte de TechRetail. Tu conocimiento se limita ESTRICTAMENTE a la información que te proporciono a continuación. NO inventes nada.\n\n"
        "**Tu Base de Conocimiento:**\n\n"
        "**1. PREGUNTAS FRECUENTES (Máxima Prioridad):**\n"
        "Usa esto para responder preguntas sobre la empresa, envíos, políticas, etc.\n"
        f"--- FAQs ---\n{faqs_context}\n---\n\n"
        "**2. CATÁLOGO DE PRODUCTOS:**\n"
        "Usa esto para responder preguntas sobre productos, stock, precios y para **dar recomendaciones si te las piden**.\n"
        f"--- PRODUCTOS ---\n{products_context}\n---\n\n"
        "**Cómo debes responder (Reglas estrictas):**\n"
        "- Primero, SIEMPRE busca la respuesta en las FAQs. Si la encuentras, úsala y no busques más.\n"
        "- Si la respuesta no está en las FAQs, búscala en el Catálogo de Productos.\n"
        "- Si un usuario te pide una **'recomendación'**, **'sugerencia'** o similar, analiza el Catálogo de Productos y sugiérele 2 o 3 artículos relevantes. No digas que no sabes.\n"
        "- **SI NO ENCUENTRAS LA RESPUESTA** en ninguna de las dos fuentes, y solo en ese caso, responde amablemente: 'Mmm, no estoy seguro de cómo responder a eso. ¿Quizás alguna de estas preguntas frecuentes te ayude?' y luego lista 3 preguntas de las FAQs que creas que se relacionan con la duda del usuario.\n\n"
        f"**Pregunta del Usuario:** \"{user_text}\""
    )
    
    bot_response_text = "No estoy seguro de cómo ayudarte con eso. Intenta reformular tu pregunta."
    try:
        response = GEMINI_MODEL.generate_content(prompt)
        bot_response_text = response.text
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text=bot_response_text
        )
    except Exception as e:
        logger.error(f"Error en la API de Gemini (texto libre): {e}")
        bot_response_text = "⚙️ Tuve un problema al procesar tu mensaje. Por favor, intenta de nuevo."
        await update.message.reply_text(bot_response_text)

    # Registrar conversación
    await log_conversation(
        user=update.effective_user,
        user_text=user_text,
        bot_text=bot_response_text
    )

# --- Función Principal ---

def main():
    """Inicia el bot de Telegram."""
    if not all([TELEGRAM_BOT_TOKEN, API_BASE_URL]):
        logger.critical("Faltan variables de entorno críticas (TELEGRAM_BOT_TOKEN o API_BASE_URL). El bot no puede iniciar.")
        return

    logger.info("Iniciando el bot...")
    
    defaults = Defaults(parse_mode=ParseMode.MARKDOWN)
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).defaults(defaults).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("productos", productos_handler))
    app.add_handler(CommandHandler("ayuda", ayuda_handler))
    app.add_handler(CommandHandler("recomendar", recomendar_handler))
    app.add_handler(CommandHandler("reservar", reservar_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    logger.info("Bot configurado y listo. Iniciando polling...")
    print("-------> BOT INICIADO Y ESCUCHANDO <-------")
    app.run_polling()
    logger.info("El bot se ha detenido.")

if __name__ == "__main__":
    main() 