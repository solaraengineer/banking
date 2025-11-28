
from django.contrib import messages
from django.db import transaction
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login as auth_login, logout
from django.views.decorators.http import require_http_methods, require_POST
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.core.mail import send_mail
from decimal import Decimal
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from .models import SupportChat, ChatMessage
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils import timezone
from datetime import timedelta
import os, json, string, jwt
from functools import wraps
from django.db.models import Count
from logic.models import User, Accounts, History
from logic.forms import RegisterForm


def require_jwt(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        token = auth_header.split(' ')[1]
        try:
            jwt.decode(token, os.getenv('JWT_SECRET'), algorithms=['HS256'])
            return view_func(request, *args, **kwargs)
        except jwt.ExpiredSignatureError:
            return JsonResponse({'error': 'Token expired'}, status=401)
        except jwt.InvalidTokenError:
            return JsonResponse({'error': 'Invalid token'}, status=401)

    return wrapper


@transaction.atomic
def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data

            if User.objects.filter(username=data['username']).exists():
                messages.error(request, 'Username already taken')
                return redirect('register')
            if User.objects.filter(email=data['email']).exists():
                messages.error(request, 'Email already taken')
                return redirect('register')

            user = User.objects.create_user(
                username=data['username'],
                password=data['password'],
                email=data['email'],
                first_name=data['first_name'],
                last_name=data['last_name'],
                phone_number=data['phone_number'],
                address=data['address'],
                city=data['city'],
                ZIP=data['ZIP'],
            )
            account = Accounts.objects.create(
                name=data['first_name'] + ' ' + data['last_name'],
                user=user,
                card_number=Accounts.generate_card_number(),
                cvv = Accounts.generate_card_cvv(),
            )
            auth_login(request, user)
            welcomeemail(user, account.card_number)
            return redirect('dashboard')
        else:
            return render(request, 'register.html', {'register_form': form})
    return render(request, 'register.html', {'register_form': RegisterForm()})


def login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        if not username or not password:
            messages.error(request, 'Please provide both username and password')
            return redirect('login')

        user = authenticate(request, username=username, password=password)

        if user:
            auth_login(request, user)
            messages.success(request, f'Welcome back, {user.first_name}!')
            return redirect('dashboard')

        messages.error(request, 'Invalid username or password')
        return redirect('login')
    return render(request, 'login.html')

@login_required(login_url='login')
def dashboard(request):
    return render(request, 'dashboard.html', {
        'user': request.user,
        'account': request.user.account,
    })


@login_required(login_url='login')
@require_http_methods(["POST"])
def addcash(request):
    try:
        data = json.loads(request.body)
        amount = data.get('amount')

        if not amount:
            return JsonResponse({'error': 'Amount is required'}, status=400)

        amount = Decimal(str(amount))

        if amount <= 0:
            return JsonResponse({'error': 'Amount must be greater than 0'}, status=400)

        account = request.user.account
        account.deposit(amount)
        deposituseremail(request.user, float(amount))

        return JsonResponse({
            'success': True,
            'message': f'Successfully deposited ${amount}',
            'new_balance': str(account.balance),
            'total_deposits': str(account.total_deposit)
        })

    except ValueError:
        return JsonResponse({'error': 'Invalid amount format'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_POST
@require_jwt
def gethistory(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        orders = data.get('orders', [])

        if not orders:
            return JsonResponse({'success': False, 'error': 'No orders provided'}, status=400)

        created_entries = []
        for order_data in orders:
            card_number = order_data.get('card_number')

            try:
                account = Accounts.objects.select_related('user').get(card_number=card_number)
                user = account.user

                history_entry = History.objects.create(
                    user=user,
                    item=order_data.get('item'),
                    status=order_data.get('status'),
                    total=Decimal(str(order_data.get('total'))),
                    order_id=order_data.get('order_id')
                )

                created_entries.append(history_entry.id)

            except Accounts.DoesNotExist:
                return JsonResponse({'success': False, 'error': f'Card {card_number} not found'}, status=404)
            except Exception as e:
                return JsonResponse({'error': str(e), 'message': 'Something went wrong'})

        return JsonResponse({
            'success': True,
            'message': f'Created {len(created_entries)} history entries',
            'entries': created_entries
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_POST
@require_jwt
def verify_card(request):
    try:
        data = json.loads(request.body)
        card_number = data.get('card_number')
        hold_name = data.get('HoldName')
        cvv = data.get('CVV')
        cart_total = data.get('cart_total')

        if not card_number or not cart_total or not hold_name or not cvv:
            return JsonResponse({'success': False, 'error': 'All card details required'}, status=400)

        with transaction.atomic():
            try:
                account = Accounts.objects.select_for_update().select_related('user').get(
                    card_number=card_number,
                    name=hold_name,
                    cvv=cvv
                )
                cart_total = Decimal(str(cart_total))

                if account.balance < cart_total:
                    return JsonResponse({
                        'success': False,
                        'error': 'Insufficient funds',
                        'balance': float(account.balance)
                    }, status=400)

                account.balance -= cart_total
                account.total_withdraw += cart_total
                account.save()

                return JsonResponse({
                    'success': True,
                    'user_id': account.user.id,
                    'balance': float(account.balance),
                    'message': 'Payment processed successfully'
                })

            except Accounts.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Invalid card details'}, status=404)

    except Exception as e:
        return JsonResponse({'success': False, 'error': 'Payment processing failed'}, status=500)

@login_required(login_url='login')
@require_http_methods(["POST"])
def withdrawcash(request):
    try:
        data = json.loads(request.body)
        amount = data.get('amount')

        if not amount:
            return JsonResponse({'error': 'Amount is required'}, status=400)

        amount = Decimal(str(amount))

        if amount <= 0:
            return JsonResponse({'error': 'Amount must be greater than 0'}, status=400)

        account = request.user.account

        if account.balance < amount:
            return JsonResponse({'error': 'Insufficient funds'}, status=400)

        success = account.withdraw(amount)

        if success:
            withdrawuseremail(request.user, amount, account.balance)
            return JsonResponse({
                'success': True,
                'message': f'Successfully withdrew ${amount}',
                'new_balance': str(account.balance),
                'total_withdrawals': str(account.total_withdraw)
            })
        return JsonResponse({'error': 'Withdrawal failed'}, status=400)

    except ValueError:
        return JsonResponse({'error': 'Invalid amount format'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out successfully')
    return redirect('login')


def deposituseremail(user, amount):
    html_message = render_to_string('userdeposit.html', {
        'user': user,
        'amount': amount,
        'customer_name': f"{user.first_name} {user.last_name}",
        'customer_email': user.email,
        'living_address': f"{user.address}, {user.city}"
    })

    send_mail(
        subject='Deposit confirmation- APEX bank',
        message=strip_tags(html_message),
        from_email='solaradeveloper@gmail.com',
        recipient_list=[user.email],
        html_message=html_message,
        fail_silently=False,
    )


def withdrawuseremail(user, amount, new_balance):
    html_message = render_to_string('userwithdraw.html', {
        'new_balance': new_balance,
        'user': user,
        'amount': amount,
        'customer_name': f"{user.first_name} {user.last_name}",
        'customer_email': user.email,
        'living_address': f"{user.address}, {user.city}"
    })

    send_mail(
        subject='Withdrawal confirmation- APEX bank',
        message=strip_tags(html_message),
        from_email='solaradeveloper@gmail.com',
        recipient_list=[user.email],
        html_message=html_message,
        fail_silently=False,
    )


def welcomeemail(user, card_number):
    html_message = render_to_string('userwelcome.html', {
        'customer_name': f"{user.first_name} {user.last_name}",
        'card_number': card_number,
    })

    send_mail(
        subject='Welcome to Apex Bank! 🎉',
        message=strip_tags(html_message),
        from_email='solaradeveloper@gmail.com',
        recipient_list=[user.email],
        html_message=html_message,
        fail_silently=False,
    )

@login_required(login_url='login')
@require_POST
def refund(request, order_id):
    try:
        with transaction.atomic():
            history_entry = History.objects.select_for_update().get(
                id=order_id,
                user=request.user
            )

            if history_entry.status == 'Refunded':
                return JsonResponse({
                    'status': 'error',
                    'message': 'Already refunded'
                }, status=400)

            if history_entry.status != 'Paid':
                return JsonResponse({
                    'status': 'error',
                    'message': 'Only paid transactions can be refunded'
                }, status=400)

            account = request.user.account

            account.balance += history_entry.total
            account.total_deposit += history_entry.total
            account.total_refund += history_entry.total
            account.save()

            history_entry.status = 'Refunded'
            history_entry.save()

            return JsonResponse({
                'status': 'success',
                'message': 'Refund successful',
                'new_balance': str(account.balance)
            })

    except History.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Transaction not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': 'Refund failed'
        }, status=500)

@login_required(login_url='login')
@require_POST
def resetbalance(request):
    account = request.user.account
    account.balance = Decimal('0.00')
    account.save()
    messages.success(request, 'Balance reset to $0.00')
    return redirect('dashboard')

@login_required
def user_support_chat(request):
    chat = SupportChat.objects.filter(user=request.user, is_active=True).first()

    if not chat:
        chat = SupportChat.objects.create(user=request.user)

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            'admin_dashboard',
            {
                'type': 'new_chat_created',
                'chat': {
                    'id': chat.id,
                    'username': chat.user.username,
                    'created_at': chat.created_at.isoformat(),
                    'message_count': 0,
                    'last_message': None
                }
            }
        )

    return render(request, 'user_chat.html', {'chat': chat})


@login_required
def admin_dashboard(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')


    cleanup_empty_chats()
    chats = SupportChat.objects.filter(is_active=True).order_by('-created_at')
    return render(request, 'admin_dashboard.html', {'chats': chats})


@login_required
def admin_chat_view(request, chat_id):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')

    try:
        chat = SupportChat.objects.get(id=chat_id)
        return render(request, 'admin_chat.html', {'chat': chat})
    except SupportChat.DoesNotExist:
        return redirect('admin_dashboard')


@login_required
@require_http_methods(["POST"])
def close_chat(request, chat_id):
    if not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    try:
        chat = SupportChat.objects.get(id=chat_id)
        chat.is_active = False
        chat.save()
        return JsonResponse({'status': 'success','message': 'Chat closed.'})
    except SupportChat.DoesNotExist:
        return JsonResponse({'error': 'Chat not found'}, status=404)


def cleanup_empty_chats():
    expiry = timezone.now() - timedelta(minutes=30)

    empty_chats = SupportChat.objects.annotate(
        msg_count=Count('messages')
    ).filter(
        is_active=True,
        created_at__lt=expiry,
        msg_count=0
    )

    count = empty_chats.count()
    empty_chats.delete()
    return count