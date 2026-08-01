"""Channel URL routing configuration."""

from apps.chat.routing import websocket_urlpatterns as ai_chat_patterns

urlpatterns: list = [] + ai_chat_patterns
