from typing import Dict, List, Any

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef


class TwilioIntegration(BaseHTTPIntegration):
    """Twilio API Integration."""

    name = "twilio"
    display_name = "Twilio"
    api_type = "rest"
    base_url = "https://api.twilio.com/2010-04-01"

    auth_scheme: Dict[str, Any] = {
        "type": "basic",
        "username_field": "account_sid",
        "password_field": "auth_token",
    }

    auth_fields: List[AuthFieldDef] = [
        AuthFieldDef(name="account_sid", label="Account SID", required=True),
        AuthFieldDef(name="auth_token", label="Auth Token", required=True),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="POST", path="/Accounts/{account_sid}/Messages.json", description="Send an SMS or MMS message"),
        EndpointDef(method="GET", path="/Accounts/{account_sid}/Messages.json", description="List messages"),
        EndpointDef(method="GET", path="/Accounts/{account_sid}/Messages/{message_sid}.json", description="Get a message"),
        EndpointDef(method="GET", path="/Accounts/{account_sid}/Calls.json", description="List calls"),
        EndpointDef(method="POST", path="/Accounts/{account_sid}/Calls.json", description="Make a phone call"),
        EndpointDef(method="GET", path="/Accounts/{account_sid}/Calls/{call_sid}.json", description="Get a call"),
        EndpointDef(method="GET", path="/Accounts/{account_sid}/IncomingPhoneNumbers.json", description="List phone numbers"),
        EndpointDef(method="GET", path="/Accounts/{account_sid}.json", description="Get account info"),
    ]

    usage_instructions = (
        "Twilio API integration. Authenticate with Account SID and Auth Token (Basic auth). Use POST /Accounts/{sid}/Messages.json to send SMS (requires 'To', 'From', 'Body'). Uses form-encoded POST bodies."
    )
