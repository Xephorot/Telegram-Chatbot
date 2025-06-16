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
        products = response.json().get('results', [])
        
        if not products:
            return "No hay productos disponibles actualmente."
            
        lines = [f"📦 ID: {p['id']} - {p['name']} - ${p['price']} (Stock: {p['stock']})" for p in products]
        return "\n".join(lines)
    except requests.RequestException as e:
        logger.error(f"Error al contactar la API de productos: {e}")
        return "Lo siento, no pude obtener la lista de productos en este momento."

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
    text = (
        "¡Hola! 👋 Soy tu asistente de compras. Esto es lo que puedo hacer:\n\n"
        "🤖 **Comandos Disponibles** 🤖\n"
        "• `/productos` - Muestra la lista de productos.\n"
        "• `/reservar <ID_del_producto> <cantidad>` - Reserva un artículo.\n"
        "• `/recomendar` - Te doy una recomendación inteligente.\n\n"
        "También puedes escribirme lo que necesites y usaré mi IA para ayudarte."
    )
    await update.message.reply_text(text)

async def productos_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para el comando /productos."""
    product_list = get_products_from_api()
    await update.message.reply_text(product_list)

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
        bot_response_text = "Tuve un problema al generar la recomendación. Por favor, intenta de nuevo."
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
    """Maneja los mensajes de texto libre usando Gemini."""
    if not GEMINI_MODEL:
        await update.message.reply_text("Lo siento, no puedo procesar tu solicitud en este momento.")
        return
        
    user_text = update.message.text
    product_list = get_products_from_api(limit=100)

    prompt = (
        "Eres un chatbot de ventas amigable y muy conciso. Tu objetivo es ayudar al usuario. "
        "Tus respuestas deben ser cortas y directas (máximo 50 palabras). "
        "Usa saltos de línea para listar elementos. No uses formato como negritas o cursiva. "
        "Usa la siguiente lista de productos como contexto. "
        "Si el usuario quiere reservar, indícale usar el comando `/reservar <ID> <cantidad>`.\n\n"
        "--- Contexto de Productos ---\n"
        f"{product_list}\n"
        "---------------------------\n\n"
        f"Usuario: \"{user_text}\"\n"
        "Respuesta concisa:"
    )
    
    bot_response_text = ""
    try:
        response = GEMINI_MODEL.generate_content(prompt)
        bot_response_text = response.text
        # Ya no usamos parse_mode para evitar errores, el prompt pide el formato.
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text=bot_response_text
        )
    except Exception as e:
        logger.error(f"Error en la API de Gemini (texto libre): {e}")
        bot_response_text = "Tuve un problema al procesar tu mensaje. Por favor, intenta de nuevo."
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
    app.add_handler(CommandHandler("recomendar", recomendar_handler))
    app.add_handler(CommandHandler("reservar", reservar_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    logger.info("Bot configurado. Iniciando polling...")
    app.run_polling()
    logger.info("El bot se ha detenido.")

if __name__ == "__main__":
    main() 