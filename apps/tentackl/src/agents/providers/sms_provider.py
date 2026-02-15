"""SMS notification provider (Twilio)"""
# REVIEW:
# - Credentials are used directly; no support for Twilio subaccounts or retry/backoff.

from typing import Any, Dict
import httpx
from src.interfaces.notification_provider import NotificationProviderInterface, NotificationResult
import base64

class SMSProvider(NotificationProviderInterface):
    """SMS provider using Twilio API"""
    
    def __init__(self, credentials: Dict[str, Any]):
        """
        Initialize SMS provider with credentials from context.
        
        Expected credentials:
        - api_key: Twilio Account SID
        - secret: Twilio Auth Token
        - from_number: Twilio phone number (optional, can be in metadata)
        """
        self.account_sid = credentials.get("api_key")  # Twilio uses Account SID as "api_key"
        self.auth_token = credentials.get("secret")
        self.from_number = credentials.get("from_number")
        
        if not self.account_sid:
            raise ValueError("SMS provider requires 'api_key' (Account SID) in credentials")
        if not self.auth_token:
            raise ValueError("SMS provider requires 'secret' (Auth Token) in credentials")
    
    def _get_auth_header(self) -> str:
        """Generate Twilio Basic Auth header"""
        credentials = f"{self.account_sid}:{self.auth_token}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"
    
    async def send(self, recipient: str, content: str, **kwargs) -> NotificationResult:
        """Send SMS via Twilio API"""
        from_number = kwargs.get("from_number", self.from_number)
        
        if not from_number:
            return NotificationResult(
                success=False,
                provider="sms",
                error="No 'from_number' provided in credentials or metadata"
            )
        
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        
        data = {
            "From": from_number,
            "To": recipient,
            "Body": content
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    url,
                    data=data,
                    headers={
                        "Authorization": self._get_auth_header()
                    }
                )
                
                if response.status_code == 201:
                    result = response.json()
                    return NotificationResult(
                        success=True,
                        provider="sms",
                        message_id=result.get("sid"),
                        metadata={"status": result.get("status")}
                    )
                else:
                    error_text = response.text
                    return NotificationResult(
                        success=False,
                        provider="sms",
                        error=f"Twilio API returned {response.status_code}: {error_text}"
                    )
        except Exception as e:
            return NotificationResult(
                success=False,
                provider="sms",
                error=str(e)
            )
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate SMS provider configuration"""
        return "api_key" in config and "secret" in config
