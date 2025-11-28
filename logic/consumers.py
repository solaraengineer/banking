import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import SupportChat, ChatMessage


class SupportChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.chat_id = self.scope['url_route']['kwargs']['chat_id']
        self.room_group_name = f'support_chat_{self.chat_id}'
        self.user = self.scope['user']

        if not self.user.is_authenticated:
            await self.close()
            return
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

        messages = await self.get_chat_history()
        await self.send(text_data=json.dumps({
            'type': 'chat_history',
            'messages': messages
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        message = data['message']

        chat_message = await self.save_message(message)


        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message,
                'sender': self.user.username,
                'timestamp': chat_message['timestamp'],
                'is_admin': chat_message['is_admin']
            }
        )

        # If admin dashboard is open, notify it about new message
        await self.channel_layer.group_send(
            'admin_dashboard',
            {
                'type': 'new_message_notification',
                'chat_id': self.chat_id,
                'message': message,
                'sender': self.user.username,
            }
        )

    async def chat_message(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message': event['message'],
            'sender': event['sender'],
            'timestamp': event['timestamp'],
            'is_admin': event['is_admin']
        }))

    @database_sync_to_async
    def get_chat_history(self):
        try:
            chat = SupportChat.objects.get(id=self.chat_id)
            messages = chat.messages.all()
            return [{
                'message': msg.message,
                'sender': msg.sender.username,
                'timestamp': msg.timestamp.isoformat(),
                'is_admin': msg.is_admin
            } for msg in messages]
        except SupportChat.DoesNotExist:
            return []

    @database_sync_to_async
    def save_message(self, message):
        chat = SupportChat.objects.get(id=self.chat_id)
        is_admin = self.user.is_staff or self.user.is_superuser

        chat_message = ChatMessage.objects.create(
            chat=chat,
            sender=self.user,
            message=message,
            is_admin=is_admin
        )

        return {
            'timestamp': chat_message.timestamp.isoformat(),
            'is_admin': is_admin
        }


class AdminDashboardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']

        if not self.user.is_authenticated or not (self.user.is_staff or self.user.is_superuser):
            await self.close()
            return


        await self.channel_layer.group_add(
            'admin_dashboard',
            self.channel_name
        )

        await self.accept()


        chats = await self.get_all_chats()
        await self.send(text_data=json.dumps({
            'type': 'all_chats',
            'chats': chats
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            'admin_dashboard',
            self.channel_name
        )

    async def receive(self, text_data):
        # Admin dashboard doesn't need to receive messages directly
        pass

    async def new_message_notification(self, event):
        # Notify admin dashboard of new message
        await self.send(text_data=json.dumps({
            'type': 'new_message',
            'chat_id': event['chat_id'],
            'message': event['message'],
            'sender': event['sender']
        }))

    async def new_chat_created(self, event):
        # Notify admin dashboard of new chat
        await self.send(text_data=json.dumps({
            'type': 'new_chat',
            'chat': event['chat']
        }))

    @database_sync_to_async
    def get_all_chats(self):
        chats = SupportChat.objects.filter(is_active=True).select_related('user')
        return [{
            'id': chat.id,
            'username': chat.user.username,
            'created_at': chat.created_at.isoformat(),
            'message_count': chat.messages.count(),
            'last_message': chat.messages.last().message if chat.messages.exists() else None
        } for chat in chats]