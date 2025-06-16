from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'categories', views.CategoryViewSet)
router.register(r'products', views.ProductViewSet)
router.register(r'users', views.UserViewSet)
router.register(r'conversations', views.ConversationViewSet)
router.register(r'messages', views.MessageViewSet)
router.register(r'orders', views.OrderViewSet)
router.register(r'faq-categories', views.FAQCategoryViewSet)
router.register(r'faqs', views.FAQViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
    path('admin/chatbot_report/', views.chatbot_report_view, name='chatbot_report'),
] 