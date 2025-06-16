from django.shortcuts import render
from rest_framework import viewsets, filters, status
from rest_framework.decorators import api_view, action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Avg
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponseForbidden
import os
import google.generativeai as genai
import logging

logger = logging.getLogger(__name__)

from .models import (
    Category, Product, User, Conversation, Message, 
    ProductComparison, Order, OrderItem, FAQ, FAQCategory
)
from .serializers import (
    CategorySerializer, ProductSerializer, UserSerializer, 
    ConversationSerializer, MessageSerializer, ProductComparisonSerializer,
    OrderSerializer, OrderItemSerializer, FAQSerializer, FAQCategorySerializer
)

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'stock']
    search_fields = ['name', 'description']
    ordering_fields = ['price', 'name', 'created_at']
    
    @action(detail=False, methods=['get'])
    def in_stock(self, request):
        in_stock = Product.objects.filter(stock__gt=0)
        serializer = self.get_serializer(in_stock, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def reserve(self, request, pk=None):
        """
        Creates or updates a pending order for a user, adds a product to it,
        and adjusts stock. This is intended to be called by the bot.
        """
        product = self.get_object()
        
        telegram_id = request.data.get('telegram_id')
        quantity_str = request.data.get('quantity')
        
        if not telegram_id or not quantity_str:
            return Response({"error": "telegram_id and quantity are required"}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            quantity = int(quantity_str)
            if quantity <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            return Response({"error": "A valid positive integer quantity is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Use get_or_create for the user
        user, _ = User.objects.get_or_create(
            telegram_id=str(telegram_id),
            defaults={
                'username': request.data.get('username'),
                'first_name': request.data.get('first_name'),
                'last_name': request.data.get('last_name'),
            }
        )

        if product.stock < quantity:
            return Response({"error": "Not enough stock available"}, status=status.HTTP_400_BAD_REQUEST)
            
        # Get or create a pending order for the user
        order, _ = Order.objects.get_or_create(
            user=user, 
            status='pending',
            defaults={'conversation': Conversation.objects.filter(user=user).last()}
        )
        
        # Create or update the order item
        OrderItem.objects.update_or_create(
            order=order, 
            product=product,
            defaults={'quantity': quantity, 'price': product.price}
        )
        
        # Update stock - this should be done carefully, ideally in a transaction
        product.stock -= quantity
        product.save()

        # Recalculate order total
        order.calculate_total()
        
        serializer = OrderSerializer(order)
        return Response(serializer.data, status=status.HTTP_200_OK)

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['username', 'first_name', 'last_name']
    filterset_fields = ['telegram_id']

class ConversationViewSet(viewsets.ModelViewSet):
    queryset = Conversation.objects.all()
    serializer_class = ConversationSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['user']
    
    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        conversation = self.get_object()
        messages = Message.objects.filter(conversation=conversation).order_by('timestamp')
        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data)

class MessageViewSet(viewsets.ModelViewSet):
    queryset = Message.objects.all()
    serializer_class = MessageSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['conversation', 'sender']

class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['user', 'status']
    ordering_fields = ['created_at', 'total_amount']
    
    @action(detail=False, methods=['get'])
    def by_user(self, request):
        user_id = request.query_params.get('user_id')
        if not user_id:
            return Response({"error": "User ID is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        orders = Order.objects.filter(user__telegram_id=user_id).order_by('-created_at')
        serializer = self.get_serializer(orders, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def add_item(self, request, pk=None):
        order = self.get_object()
        
        product_id = request.data.get('product_id')
        quantity = request.data.get('quantity', 1)
        
        if not product_id:
            return Response({"error": "Product ID is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            product = Product.objects.get(pk=product_id)
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)
        
        if product.stock < quantity:
            return Response({"error": "Not enough stock available"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Crear o actualizar el item del pedido
        order_item, created = OrderItem.objects.update_or_create(
            order=order,
            product=product,
            defaults={'quantity': quantity, 'price': product.price}
        )
        
        # Actualizar el monto total del pedido
        order_items = OrderItem.objects.filter(order=order)
        total_amount = sum(item.price * item.quantity for item in order_items)
        order.total_amount = total_amount
        order.save()
        
        serializer = OrderItemSerializer(order_item)
        return Response(serializer.data)
        
    @action(detail=True, methods=['delete'])
    def cancel(self, request, pk=None):
        """Cancela un pedido completo marcándolo como cancelled."""
        order = self.get_object()
        logger.info(f"Cancelando pedido {order.id} para usuario {order.user.telegram_id}")
        
        # Restaurar el stock de los productos
        try:
            for item in order.items.all():
                product = item.product
                product.stock += item.quantity
                product.save()
                logger.info(f"Stock restaurado para producto {product.id}: +{item.quantity} unidades")
        except Exception as e:
            logger.error(f"Error al restaurar stock en cancelación de pedido {order.id}: {e}")
        
        # Marcar como cancelado
        order.status = 'cancelled'
        order.save()
        
        logger.info(f"Pedido {order.id} marcado como cancelado exitosamente")
        return Response({"status": "cancelled", "message": "Pedido cancelado exitosamente"}, 
                        status=status.HTTP_200_OK)

class OrderItemViewSet(viewsets.ModelViewSet):
    queryset = OrderItem.objects.all()
    serializer_class = OrderItemSerializer
    
    def destroy(self, request, *args, **kwargs):
        """Elimina un item de pedido y actualiza el total del pedido."""
        item = self.get_object()
        order = item.order
        product = item.product
        quantity = item.quantity
        
        logger.info(f"Eliminando item {item.id} del pedido {order.id}")
        
        # Restaurar el stock del producto
        try:
            product.stock += quantity
            product.save()
            logger.info(f"Stock restaurado para producto {product.id}: +{quantity} unidades")
        except Exception as e:
            logger.error(f"Error al restaurar stock: {e}")
        
        # Eliminar el item
        item.delete()
        
        # Recalcular el total del pedido
        order.calculate_total()
        
        logger.info(f"Item eliminado y pedido recalculado: {order.total_amount}")
        return Response(status=status.HTTP_204_NO_CONTENT)

class FAQCategoryViewSet(viewsets.ModelViewSet):
    queryset = FAQCategory.objects.all()
    serializer_class = FAQCategorySerializer

class FAQViewSet(viewsets.ModelViewSet):
    queryset = FAQ.objects.all()
    serializer_class = FAQSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['category']
    search_fields = ['question', 'answer']

def chatbot_report_view(request):
    """
    Vista de reporte del chatbot.

    Si se recibe el parámetro GET ``telegram_id`` (o ``user_id``), el reporte se filtra
    únicamente para ese usuario.  De lo contrario, se muestran métricas globales.
    """

    # --- Detección de filtro por usuario ---
    telegram_param = request.GET.get('telegram_id') or request.GET.get('user_id')
    user_obj = None
    if telegram_param:
        user_obj = User.objects.filter(telegram_id=str(telegram_param)).first()

    if user_obj:
        # Métricas para un solo usuario
        total_users = 1
        total_conversations = Conversation.objects.filter(user=user_obj).count()
        total_messages = Message.objects.filter(conversation__user=user_obj).count()
        avg_order_value = (
            Order.objects.filter(user=user_obj).aggregate(avg_value=Avg('total_amount'))['avg_value']
            or 0
        )
    else:
        # Métricas globales
        total_users = User.objects.count()
        total_conversations = Conversation.objects.count()
        total_messages = Message.objects.count()
        avg_order_value = Order.objects.aggregate(avg_value=Avg('total_amount'))['avg_value'] or 0

    # 2. Análisis con IA (si la clave está disponible)
    gemini_analysis = {
        'main_topics': 'No disponible. Configura la GEMINI_API_KEY.',
        'general_sentiment': 'No disponible.',
        'improvement_suggestions': 'No disponible.'
    }
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            
            # Recopilar los últimos 100 mensajes de usuarios para análisis (filtrado por usuario si aplica)
            msg_queryset = Message.objects.filter(sender='user')
            if user_obj:
                msg_queryset = msg_queryset.filter(conversation__user=user_obj)

            recent_user_messages = msg_queryset.order_by('-timestamp')[:100]

            if recent_user_messages:
                messages_text = "\n".join([f"- \"{msg.content}\"" for msg in recent_user_messages])
                prompt = (
                    "Eres un analista de datos experto en experiencia de cliente. "
                    "Analiza los siguientes mensajes de usuarios de un chatbot de ventas. "
                    "Basado en estos mensajes, proporciona un resumen en 3 secciones:\n\n"
                    "1.  **Temas Principales:** Identifica y lista los 3-5 temas más recurrentes (ej: 'dudas sobre envíos', 'interés en celulares').\n"
                    "2.  **Sentimiento General:** Describe el sentimiento predominante (Positivo, Negativo, Neutro) y justifica brevemente.\n"
                    "3.  **Sugerencias de Mejora:** Basado en los temas y el sentimiento, sugiere 1 o 2 acciones concretas para mejorar el bot o el servicio (ej: 'Añadir una FAQ sobre métodos de pago', 'Mejorar la descripción del producto X').\n\n"
                    "Sé claro, conciso y profesional. No uses formato Markdown.\n\n"
                    "--- MENSAJES DE USUARIOS ---\n"
                    f"{messages_text}\n"
                    "--- FIN DE MENSAJES ---\n\n"
                    "Análisis:"
                )
                
                response = model.generate_content(prompt)
                
                analysis_text = response.text
                
                # Normalizamos encabezados quitando numeración ("1.", "2." ...)
                import re
                cleaned_text = re.sub(r"\n?\s*\d+\.\s*(Temas Principales|Sentimiento General|Sugerencias de Mejora):", r"\n\1:", analysis_text)

                # Extraemos cada sección de forma robusta
                def extract_section(label: str, text: str) -> str:
                    pattern = re.compile(rf"{label}:\s*(.*?)\s*(?:(Temas Principales|Sentimiento General|Sugerencias de Mejora):|$)", re.S)
                    match = pattern.search(text)
                    return match.group(1).strip() if match else "N/A"

                gemini_analysis['main_topics'] = extract_section("Temas Principales", cleaned_text)
                gemini_analysis['general_sentiment'] = extract_section("Sentimiento General", cleaned_text)
                gemini_analysis['improvement_suggestions'] = extract_section("Sugerencias de Mejora", cleaned_text)

            else:
                gemini_analysis['main_topics'] = "No hay suficientes mensajes de usuarios para analizar."
                gemini_analysis['general_sentiment'] = "N/A"
                gemini_analysis['improvement_suggestions'] = "N/A"

        except Exception as e:
            # Manejo de error si la API de Gemini falla
            error_message = f"Error al contactar la API de Gemini: {e}"
            gemini_analysis['main_topics'] = error_message
            gemini_analysis['general_sentiment'] = "Error"
            gemini_analysis['improvement_suggestions'] = "Error"
            logger.error(error_message)

    title = 'Reporte del Chatbot'
    if user_obj:
        nice_name = user_obj.username or user_obj.first_name or user_obj.telegram_id
        title = f"Reporte del Usuario: {nice_name}"

    context = { 
        'title': title,
        'total_users': total_users,
        'total_conversations': total_conversations,
        'total_messages': total_messages,
        'avg_order_value': avg_order_value,
        'gemini_analysis': gemini_analysis,
        'has_gemini_key': bool(gemini_key),
        'user_report': bool(user_obj),
        'report_user': user_obj,
    }
    
    return render(request, 'admin/chatbot_report.html', context)
