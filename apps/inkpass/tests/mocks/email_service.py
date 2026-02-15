"""Mock email service for testing"""

from typing import List, Dict, Any

# Store sent emails in memory for testing
sent_emails: List[Dict[str, Any]] = []


def send_email(to: str, subject: str, body: str) -> bool:
    """Mock email sending - stores email in memory"""
    sent_emails.append({
        "to": to,
        "subject": subject,
        "body": body
    })
    return True


def get_sent_emails() -> List[Dict[str, Any]]:
    """Get all sent emails"""
    return sent_emails.copy()


def clear_sent_emails():
    """Clear sent emails"""
    sent_emails.clear()


def get_latest_email(to: str = None) -> Dict[str, Any]:
    """Get the latest email sent, optionally filtered by recipient"""
    if to:
        for email in reversed(sent_emails):
            if email["to"] == to:
                return email
    return sent_emails[-1] if sent_emails else None


