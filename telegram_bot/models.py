from django.db import models
from django.utils import timezone

class Category(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name_plural = "Categories"

class Product(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.ForeignKey(Category, related_name='products', on_delete=models.CASCADE)
    image_url = models.URLField(blank=True, null=True)
    stock = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name

class User(models.Model):
    telegram_id = models.CharField(max_length=100, unique=True)
    username = models.CharField(max_length=100, blank=True, null=True)
    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.username or str(self.telegram_id)

class Conversation(models.Model):
    user = models.ForeignKey(User, related_name='conversations', on_delete=models.CASCADE)
    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(blank=True, null=True)
    
    def __str__(self):
        return f"Conversation with {self.user} at {self.start_time}"

class Message(models.Model):
    SENDER_CHOICES = (
        ('user', 'User'),
        ('bot', 'Bot'),
    )
    
    conversation = models.ForeignKey(Conversation, related_name='messages', on_delete=models.CASCADE)
    sender = models.CharField(max_length=10, choices=SENDER_CHOICES)
    content = models.TextField()
    timestamp = models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        return f"{self.sender} message at {self.timestamp}"

class ProductComparison(models.Model):
    conversation = models.ForeignKey(Conversation, related_name='comparisons', on_delete=models.CASCADE)
    products = models.ManyToManyField(Product, related_name='comparisons')
    timestamp = models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        return f"Comparison at {self.timestamp}"

class Order(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    )
    
    user = models.ForeignKey(User, related_name='orders', on_delete=models.CASCADE)
    conversation = models.ForeignKey(Conversation, related_name='orders', on_delete=models.SET_NULL, null=True, blank=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Order {self.id} by {self.user}"

    def calculate_total(self):
        """Calculates or recalculates the total amount of the order from its items."""
        self.total_amount = sum(item.get_item_price() for item in self.items.all())
        self.save()

class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, related_name='order_items', on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)  # Price at the time of purchase
    
    def __str__(self):
        return f"{self.quantity} x {self.product.name}"

    def get_item_price(self):
        """Returns the total price for this line item."""
        return self.price * self.quantity

class FAQCategory(models.Model):
    name = models.CharField(max_length=100)
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name_plural = "FAQ Categories"

class FAQ(models.Model):
    question = models.TextField()
    answer = models.TextField()
    category = models.ForeignKey(FAQCategory, related_name='faqs', on_delete=models.CASCADE)
    
    def __str__(self):
        return self.question
