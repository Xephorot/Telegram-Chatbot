from django.core.management.base import BaseCommand
import logging
import os

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

import google.generativeai as genai

from telegram_bot.models import (
    Product,
    Category,
    User as BotUser,
    Conversation,
    Message as BotMessage,
    Order,
    OrderItem,
)

logger = logging.getLogger(__name__)


# ----------------------------
# Helper functions
# ----------------------------

def _format_product_list(limit: int = 20) -> str:
    """Return a human-readable list of products limited to *limit* entries."""
    products = Product.objects.all()[:limit]
    if not products:
        return "No hay productos disponibles actualmente."

    lines = [
        f"{p.id}. {p.name} — ${p.price} (stock: {p.stock})" for p in products
    ]
    return "\n".join(lines)


def _ensure_user(update: Update) -> BotUser:
    telegram_user = update.effective_user
    defaults = {
        "username": telegram_user.username,
        "first_name": telegram_user.first_name,
        "last_name": telegram_user.last_name,
    }
    user, _ = BotUser.objects.update_or_create(
        telegram_id=str(telegram_user.id), defaults=defaults
    )
    return user


def _log_message(conv: Conversation, sender: str, text: str):
    BotMessage.objects.create(conversation=conv, sender=sender, content=text)


# ----------------------------
# Gemini integration
# ----------------------------

def _init_gemini():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Env var GEMINI_API_KEY is required to run the bot.")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-pro")


GEMINI_MODEL = None  # Lazy init


async def _gemini_response(prompt: str) -> str:
    global GEMINI_MODEL
    if GEMINI_MODEL is None:
        GEMINI_MODEL = _init_gemini()

    try:
        response = GEMINI_MODEL.generate_content(prompt)
        # The SDK returns a GenerativeResponse. `.text` has the answer.
        return response.text
    except Exception as exc:
        logger.exception("Gemini API error: %s", exc)
        return "Lo siento, ocurrió un error al procesar tu solicitud. Por favor, inténtalo de nuevo más tarde."


# ----------------------------
# Telegram handlers
# ----------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start command handler."""
    user = _ensure_user(update)

    text = (
        "¡Hola! Soy tu asistente virtual 🤖. \n\n"
        "Puedo ayudarte a:\n"
        "• Ver la lista de productos disponibles (/productos)\n"
        "• Obtener una cotización (/cotizar <producto_id> <cantidad>)\n"
        "• Reservar un producto (/reservar <producto_id> <cantidad>)\n"
        "• Obtener recomendaciones (/recomendar)\n\n"
        "También puedes escribirme de forma natural y usaré IA para responder."
    )
    await update.message.reply_text(text)


async def productos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a list of available products."""
    _ensure_user(update)
    products_text = _format_product_list()
    await update.message.reply_text(products_text)


async def cotizar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return a price quote for a product."""
    user = _ensure_user(update)
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Uso: /cotizar <producto_id> <cantidad>", quote=True
        )
        return

    try:
        product_id = int(args[0])
        quantity = int(args[1])
    except ValueError:
        await update.message.reply_text("ID de producto y cantidad deben ser números.")
        return

    product = Product.objects.filter(id=product_id).first()
    if not product:
        await update.message.reply_text("Producto no encontrado.")
        return

    total = product.price * quantity
    text = f"La cotización para {quantity} x {product.name} es: ${float(total):.2f}"
    await update.message.reply_text(text)


async def reservar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reserve a product (creates an order with pending status)."""
    user = _ensure_user(update)
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Uso: /reservar <producto_id> <cantidad>")
        return

    try:
        product_id = int(args[0])
        quantity = int(args[1])
    except ValueError:
        await update.message.reply_text("ID de producto y cantidad deben ser números.")
        return

    product = Product.objects.filter(id=product_id).first()
    if not product:
        await update.message.reply_text("Producto no encontrado.")
        return

    if product.stock < quantity:
        await update.message.reply_text("Lo sentimos, no hay suficiente stock disponible.")
        return

    # Create conversation if not exists
    conversation, _ = Conversation.objects.get_or_create(
        user=user, end_time=None
    )

    # Create order or update existing pending order
    order, _ = Order.objects.get_or_create(
        user=user, status="pending", defaults={"total_amount": 0, "conversation": conversation}
    )

    OrderItem.objects.create(order=order, product=product, quantity=quantity, price=product.price)

    # Reduce stock
    product.stock -= quantity
    product.save()

    # Recalculate order total
    total = sum(item.price * item.quantity for item in order.items.all())
    order.total_amount = total
    order.save()

    await update.message.reply_text(
        f"Reserva realizada ✅. Tu pedido (ID: {order.id}) se creó con un total de ${float(total):.2f}."
    )


async def recomendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Use Gemini to recommend items."""
    user = _ensure_user(update)

    prompt = (
        "Eres un asistente de ventas. Basado en la siguiente lista de productos, "
        "recomienda los 3 artículos que creas que gustarán más a un cliente típico y explica brevemente por qué.\n\n"
        f"Lista de productos disponibles:\n{_format_product_list(limit=50)}"
    )
    response = await _gemini_response(prompt)
    await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Default message handler passing free-form text to Gemini."""
    user = _ensure_user(update)

    conversation, _ = Conversation.objects.get_or_create(user=user, end_time=None)

    user_text = update.message.text
    _log_message(conversation, "user", user_text)

    # ---------------- Heuristics before invoking Gemini ----------------
    user_text_lower = user_text.lower()

    # 1. Catálogo completo
    if any(word in user_text_lower for word in ["catálogo", "catalogo", "productos disponibles", "catalogo completo", "todo el catalogo"]):
        products_text = _format_product_list(limit=100)
        _log_message(conversation, "bot", products_text)
        await update.message.reply_text(products_text)
        return

    # 2. Solicitud de productos por categoría (coincidencia exacta del nombre)
    for category in Category.objects.all():
        if category.name.lower() in user_text_lower:
            products = Product.objects.filter(category=category)
            if products.exists():
                lines = [f"{p.id}. {p.name} — ${p.price} (stock: {p.stock})" for p in products]
                text = "\n".join(lines)
            else:
                text = f"Actualmente no hay productos en la categoría {category.name}."
            _log_message(conversation, "bot", text)
            await update.message.reply_text(text)
            return

    # ---------------- Gemini fallback ----------------
    # Build context and prompt
    prompt = (
        "Eres un chatbot de ventas amigable para una tienda. "
        "Aquí está la lista de productos disponibles (ID, nombre, precio, stock):\n"
        f"{_format_product_list(limit=100)}\n\n"
        "Cuando el usuario haga preguntas o solicitudes, responde de forma clara en español. "
        "Si el usuario pide cotización, calcula el precio; si pide reserva, indicale usar el comando /reservar. "
        "Mantén las respuestas breves y útiles.\n\n"
        f"Usuario: {user_text}\nBot:"
    )
    bot_text = await _gemini_response(prompt)
    _log_message(conversation, "bot", bot_text)

    await update.message.reply_text(bot_text, parse_mode=ParseMode.MARKDOWN)


# ----------------------------
# Main command
# ----------------------------

class Command(BaseCommand):
    help = "Inicia el bot de Telegram integrado con Gemini."

    async def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("--- Iniciando el comando run_bot ---"))

        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token:
            self.stderr.write(
                self.style.ERROR("FATAL: La variable de entorno TELEGRAM_BOT_TOKEN no está definida.")
            )
            return

        gemini_key = os.environ.get("GEMINI_API_KEY")
        if not gemini_key:
            self.stderr.write(
                self.style.ERROR("FATAL: La variable de entorno GEMINI_API_KEY no está definida.")
            )
            return

        self.stdout.write(self.style.SUCCESS("Tokens de Telegram y Gemini encontrados. Configurando bot..."))

        logging.basicConfig(
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
        )

        defaults = Defaults(parse_mode=ParseMode.MARKDOWN)
        app = (
            ApplicationBuilder()
            .token(token)
            .defaults(defaults)
            .build()
        )

        # Register handlers
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("productos", productos))
        app.add_handler(CommandHandler("cotizar", cotizar))
        app.add_handler(CommandHandler("reservar", reservar))
        app.add_handler(CommandHandler("recomendar", recomendar))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        self.stdout.write(self.style.SUCCESS("Eliminando webhook anterior (si existe) y comenzando polling..."))

        # Iniciar el bot en modo asíncrono
        async with app:
            try:
                await app.bot.delete_webhook(drop_pending_updates=True)
                self.stdout.write(self.style.SUCCESS("Webhook eliminado correctamente."))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"No se pudo eliminar el webhook, puede que no existiera. Error: {e}"))

            self.stdout.write(self.style.SUCCESS("🤖 Bot de Telegram iniciado. Esperando updates..."))
            await app.start_polling(drop_pending_updates=True)
            await app.run_until_disconnected() 