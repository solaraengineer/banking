import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
import random


class User(AbstractUser):
    phone_number = models.CharField(max_length=13, unique=True)
    address = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    ZIP = models.CharField(max_length=10)

class SupportChat(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='support_chats')
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Chat {self.id} - {self.user.username}"


class ChatMessage(models.Model):
    chat = models.ForeignKey(SupportChat, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_admin = models.BooleanField(default=False)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.sender.username}: {self.message[:50]}"


class History(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    total = models.DecimalField(decimal_places=2, max_digits=10)
    item = models.CharField(max_length=2500)
    date = models.DateTimeField(auto_now_add=True)
    order_id = models.CharField(max_length=50, editable=False)
    status = models.CharField(max_length=20, default='pending')

    class Meta:
        ordering = ['-date']
        verbose_name = "Transaction History"
        verbose_name_plural = "Transaction Histories"

    def __str__(self):
        return f"{self.user.username} - {self.item} - ${self.total}"


class Accounts(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='account')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_deposit = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_withdraw = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_refund = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    name = models.CharField(max_length=100,default="")
    card_number = models.CharField(max_length=16, unique=True)
    cvv = models.CharField(max_length=16,default='FAILED')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Account"
        verbose_name_plural = "Accounts"

    def __str__(self):
        return f"{self.user.username}'s Account - ${self.balance}"

    @staticmethod
    def generate_card_number():
        while True:
            card_number = ''.join([str(random.randint(0, 9)) for _ in range(16)])
            if not Accounts.objects.filter(card_number=card_number).exists():
                return card_number
    @staticmethod
    def generate_card_cvv():
        while True:
            cvv = ''.join([str(random.randint(0, 9)) for _ in range(3)])
            if not Accounts.objects.filter(cvv=cvv).exists():
                return cvv


    def deposit(self, amount):
        from decimal import Decimal
        amount = Decimal(str(amount))
        self.balance += amount
        self.total_deposit += amount
        self.save()

    def withdraw(self, amount):
        from decimal import Decimal
        amount = Decimal(str(amount))
        if self.balance >= amount:
            self.balance -= amount
            self.total_withdraw += amount
            self.save()
            return True
        return False