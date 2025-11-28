# logic/tests.py
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from decimal import Decimal
import json
import jwt
import os
from datetime import datetime, timedelta
from logic.models import User, Accounts, History

User = get_user_model()


class AccountModelTestCase(TestCase):
    """Test the Accounts model methods"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com',
            first_name='Test',
            last_name='User',
            phone_number='123456789',
            address='Test St',
            city='Warsaw',
            ZIP='00-000'
        )
        self.account = Accounts.objects.create(
            user=self.user,
            card_number='1234567890123456',
            balance=Decimal('1000.00'),
            total_deposit=Decimal('0.00'),
            total_withdraw=Decimal('0.00')
        )

    def test_deposit_increases_balance(self):
        """Test that deposit adds money correctly"""
        initial_balance = self.account.balance
        self.account.deposit(Decimal('100.00'))

        self.account.refresh_from_db()
        self.assertEqual(
            self.account.balance,
            initial_balance + Decimal('100.00')
        )
        self.assertEqual(
            self.account.total_deposit,
            Decimal('100.00')
        )

    def test_withdraw_decreases_balance(self):
        """Test that withdraw removes money correctly"""
        self.account.balance = Decimal('500.00')
        self.account.save()

        result = self.account.withdraw(Decimal('100.00'))

        self.assertTrue(result)
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal('400.00'))
        self.assertEqual(self.account.total_withdraw, Decimal('100.00'))

    def test_withdraw_fails_insufficient_funds(self):
        """Test that withdraw fails when not enough money"""
        self.account.balance = Decimal('50.00')
        self.account.save()

        result = self.account.withdraw(Decimal('100.00'))

        self.assertFalse(result)
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal('50.00'))
        self.assertEqual(self.account.total_withdraw, Decimal('0.00'))

    def test_multiple_deposits(self):
        """Test multiple deposits accumulate correctly"""
        self.account.deposit(Decimal('50.00'))
        self.account.deposit(Decimal('75.00'))
        self.account.deposit(Decimal('25.00'))

        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal('1150.00'))
        self.assertEqual(self.account.total_deposit, Decimal('150.00'))


class CardVerificationAPITestCase(TestCase):
    """Test the /api/verify endpoint"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='buyer',
            password='pass123',
            email='buyer@example.com',
            first_name='Buyer',
            last_name='Test'
        )
        self.account = Accounts.objects.create(
            user=self.user,
            card_number='1234567890123456',
            balance=Decimal('1000.00')
        )

        # Generate valid JWT token
        self.token = jwt.encode(
            {
                'service': 'ecommerce',
                'exp': datetime.utcnow() + timedelta(minutes=15)
            },
            os.getenv('JWT_SECRET'),
            algorithm='HS256'
        )

    def test_verify_card_success(self):
        """Test successful payment with sufficient funds"""
        response = self.client.post(
            '/api/verify',
            data=json.dumps({
                'card_number': '1234567890123456',
                'cart_total': '50.00'
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['user_id'], self.user.id)
        self.assertEqual(float(data['balance']), 950.0)

        # Check balance was actually deducted
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal('950.00'))
        self.assertEqual(self.account.total_withdraw, Decimal('50.00'))

    def test_verify_card_insufficient_funds(self):
        """Test payment fails with insufficient funds"""
        self.account.balance = Decimal('10.00')
        self.account.save()

        response = self.client.post(
            '/api/verify',
            data=json.dumps({
                'card_number': '1234567890123456',
                'cart_total': '50.00'
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], 'Insufficient funds')

        # Balance should not change
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal('10.00'))

    def test_verify_card_invalid_card_number(self):
        """Test payment fails with non-existent card"""
        response = self.client.post(
            '/api/verify',
            data=json.dumps({
                'card_number': '9999999999999999',
                'cart_total': '50.00'
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )

        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], 'Invalid card number')

    def test_verify_card_no_jwt_token(self):
        """Test endpoint rejects requests without JWT token"""
        response = self.client.post(
            '/api/verify',
            data=json.dumps({
                'card_number': '1234567890123456',
                'cart_total': '50.00'
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertEqual(data['error'], 'Unauthorized')

    def test_verify_card_expired_jwt_token(self):
        """Test endpoint rejects expired JWT tokens"""
        expired_token = jwt.encode(
            {
                'service': 'ecommerce',
                'exp': datetime.utcnow() - timedelta(minutes=1)
            },
            os.getenv('JWT_SECRET'),
            algorithm='HS256'
        )

        response = self.client.post(
            '/api/verify',
            data=json.dumps({
                'card_number': '1234567890123456',
                'cart_total': '50.00'
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {expired_token}'
        )

        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertEqual(data['error'], 'Token expired')

    def test_verify_card_missing_data(self):
        """Test endpoint validates required fields"""
        response = self.client.post(
            '/api/verify',
            data=json.dumps({'card_number': '1234567890123456'}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )

        self.assertEqual(response.status_code, 400)


class HistoryAPITestCase(TestCase):
    """Test the /api/gethistory endpoint"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='historyuser',
            password='pass123',
            email='history@example.com'
        )
        self.account = Accounts.objects.create(
            user=self.user,
            card_number='1111222233334444'
        )

        self.token = jwt.encode(
            {
                'service': 'ecommerce',
                'exp': datetime.utcnow() + timedelta(minutes=15)
            },
            os.getenv('JWT_SECRET'),
            algorithm='HS256'
        )

    def test_create_history_entry(self):
        """Test creating order history entries"""
        response = self.client.post(
            '/api/gethistory',
            data=json.dumps({
                'orders': [{
                    'card_number': '1111222233334444',
                    'item': 'Test Product x2',
                    'status': 'Paid',
                    'total': '99.99',
                    'order_id': '#ABC123'
                }]
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['entries']), 1)

        # Check history was created in database
        history = History.objects.filter(user=self.user).first()
        self.assertIsNotNone(history)
        self.assertEqual(history.item, 'Test Product x2')
        self.assertEqual(history.status, 'Paid')
        self.assertEqual(history.total, Decimal('99.99'))
        self.assertEqual(history.order_id, '#ABC123')

    def test_create_multiple_history_entries(self):
        """Test creating multiple order history entries at once"""
        response = self.client.post(
            '/api/gethistory',
            data=json.dumps({
                'orders': [
                    {
                        'card_number': '1111222233334444',
                        'item': 'Product A',
                        'status': 'Paid',
                        'total': '50.00',
                        'order_id': '#ORDER1'
                    },
                    {
                        'card_number': '1111222233334444',
                        'item': 'Product B',
                        'status': 'Paid',
                        'total': '75.00',
                        'order_id': '#ORDER2'
                    }
                ]
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['entries']), 2)

        # Check both entries exist
        history_count = History.objects.filter(user=self.user).count()
        self.assertEqual(history_count, 2)

    def test_history_invalid_card(self):
        """Test history endpoint rejects invalid card numbers"""
        response = self.client.post(
            '/api/gethistory',
            data=json.dumps({
                'orders': [{
                    'card_number': '9999999999999999',
                    'item': 'Test Product',
                    'status': 'Paid',
                    'total': '50.00',
                    'order_id': '#TEST123'
                }]
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )

        self.assertEqual(response.status_code, 404)


class UserDepositWithdrawViewTestCase(TestCase):
    """Test the user-facing deposit/withdraw views"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='webuser',
            password='pass123',
            email='web@example.com',
            first_name='Web',
            last_name='User'
        )
        self.account = Accounts.objects.create(
            user=self.user,
            card_number='5555666677778888',
            balance=Decimal('500.00')
        )
        self.client.login(username='webuser', password='pass123')

    def test_addcash_success(self):
        """Test user can deposit money"""
        response = self.client.post(
            '/addcash/',
            data=json.dumps({'amount': '100.00'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['new_balance'], '600.00')

        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal('600.00'))

    def test_addcash_negative_amount(self):
        """Test deposit rejects negative amounts"""
        response = self.client.post(
            '/addcash/',
            data=json.dumps({'amount': '-50.00'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)

    def test_withdrawcash_success(self):
        """Test user can withdraw money"""
        response = self.client.post(
            '/withdrawcash/',
            data=json.dumps({'amount': '100.00'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['new_balance'], '400.00')

        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal('400.00'))

    def test_withdrawcash_insufficient_funds(self):
        response = self.client.post(
            '/withdrawcash/',
            data=json.dumps({'amount': '1000.00'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data['error'], 'Insufficient funds')

        # Balance should not change
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal('500.00'))
