from typing import Dict, List, Any

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef


class TelegramBotIntegration(BaseHTTPIntegration):
    """Telegram Bot API Integration."""

    name = "telegram"
    display_name = "Telegram Bot"
    api_type = "rest"
    base_url = "https://api.telegram.org"

    auth_scheme: Dict[str, Any] = {
        "type": "bearer",
        "token_field": "bot_token",
    }

    auth_fields: List[AuthFieldDef] = [
        AuthFieldDef(name="bot_token", label="Bot Token (from @BotFather)", required=True),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="POST", path="/bot{bot_token}/sendMessage", description="Send a text message"),
        EndpointDef(method="POST", path="/bot{bot_token}/getMe", description="Get bot info"),
        EndpointDef(method="POST", path="/bot{bot_token}/getUpdates", description="Get incoming updates"),
        EndpointDef(method="POST", path="/bot{bot_token}/sendPhoto", description="Send a photo"),
        EndpointDef(method="POST", path="/bot{bot_token}/sendDocument", description="Send a document"),
        EndpointDef(method="POST", path="/bot{bot_token}/setWebhook", description="Set webhook URL"),
        EndpointDef(method="POST", path="/bot{bot_token}/deleteWebhook", description="Delete webhook"),
        EndpointDef(method="POST", path="/bot{bot_token}/getChat", description="Get chat info"),
        EndpointDef(method="POST", path="/bot{bot_token}/getChatMember", description="Get chat member info"),
    ]

    usage_instructions = (
        "Telegram Bot API integration. Authenticate with Bot Token from @BotFather. The token is embedded in the URL path: /bot{token}/method. Use sendMessage with 'chat_id' and 'text' to send messages."
    )
