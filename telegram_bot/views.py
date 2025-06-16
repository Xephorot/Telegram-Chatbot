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
    Una vista pública para mostrar métricas y análisis del chatbot.
    (Prototipo sin seguridad).
    """
    # 1. Métricas Numéricas
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
            
            # Recopilar los últimos 100 mensajes de usuarios para análisis
            recent_user_messages = Message.objects.filter(sender='user').order_by('-timestamp')[:100]
            messages_text = "\n".join([f"- \"{msg.content}\"" for msg in recent_user_messages])

            if messages_text:
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
                
                # Parsing más robusto para la respuesta del modelo
                # Se busca cada sección por su título para evitar errores si el formato cambia
                topics_part = analysis_text.split("Sentimiento General:")[0]
                sentiment_part = analysis_text.split("Sugerencias de Mejora:")[0]
                suggestions_part = analysis_text

                if "Temas Principales:" in topics_part:
                    gemini_analysis['main_topics'] = topics_part.replace("1. Temas Principales:", "").strip()
                
                if "Sentimiento General:" in sentiment_part:
                    gemini_analysis['general_sentiment'] = sentiment_part.split("Sentimiento General:")[-1].strip()
                
                if "Sugerencias de Mejora:" in suggestions_part:
                    gemini_analysis['improvement_suggestions'] = suggestions_part.split("Sugerencias de Mejora:")[-1].strip()

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

    context = { 
        'title': 'Reporte del Chatbot',
        'total_users': total_users,
        'total_conversations': total_conversations,
        'total_messages': total_messages,
        'avg_order_value': avg_order_value,
        'gemini_analysis': gemini_analysis,
        'has_gemini_key': bool(gemini_key),
    }
    
    return render(request, 'admin/chatbot_report.html', context)
