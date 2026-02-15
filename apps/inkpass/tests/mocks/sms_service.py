"""Mock SMS service for testing"""

from typing import List, Dict, Any

# Store sent SMS in memory for testing
sent_sms: List[Dict[str, Any]] = []


def send_sms(to: str, message: str) -> bool:
    """Mock SMS sending - stores SMS in memory"""
    sent_sms.append({
        "to": to,
        "message": message
    })
    return True


def get_sent_sms() -> List[Dict[str, Any]]:
    """Get all sent SMS"""
    return sent_sms.copy()


def clear_sent_sms():
    """Clear sent SMS"""
    sent_sms.clear()


def get_latest_sms(to: str = None) -> Dict[str, Any]:
    """Get the latest SMS sent, optionally filtered by recipient"""
    if to:
        for sms in reversed(sent_sms):
            if sms["to"] == to:
                return sms
    return sent_sms[-1] if sent_sms else None


