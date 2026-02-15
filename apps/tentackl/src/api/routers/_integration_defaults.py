# REVIEW:
# - Hard-coded defaults in code; may drift from provider definitions elsewhere (Mimic) and are not configurable at runtime.
"""Default outbound/inbound configurations per integration provider.

Used by the create_integration endpoint to auto-configure integrations
so they're functional immediately after creation.
"""

from typing import Optional, TypedDict


class OutboundDefaults(TypedDict):
    action_type: str
    rate_limit_requests: int
    rate_limit_window_seconds: int


class InboundDefaults(TypedDict):
    auth_method: str
    destination_service: str


class ProviderDefaults(TypedDict):
    outbound: Optional[OutboundDefaults]
    inbound: Optional[InboundDefaults]


PROVIDER_DEFAULTS: dict[str, ProviderDefaults] = {
    "discord": {
        "outbound": {
            "action_type": "send_message",
            "rate_limit_requests": 30,
            "rate_limit_window_seconds": 60,
        },
        "inbound": {
            "auth_method": "none",
            "destination_service": "tentackl",
        },
    },
    "slack": {
        "outbound": {
            "action_type": "send_message",
            "rate_limit_requests": 1,
            "rate_limit_window_seconds": 1,
        },
        "inbound": {
            "auth_method": "none",
            "destination_service": "tentackl",
        },
    },
    "github": {
        "outbound": {
            "action_type": "create_issue",
            "rate_limit_requests": 30,
            "rate_limit_window_seconds": 60,
        },
        "inbound": {
            "auth_method": "none",
            "destination_service": "tentackl",
        },
    },
    "stripe": {
        "outbound": None,  # Stripe is inbound-only
        "inbound": {
            "auth_method": "signature",
            "destination_service": "tentackl",
        },
    },
    "twitter": {
        "outbound": {
            "action_type": "send_message",
            "rate_limit_requests": 300,
            "rate_limit_window_seconds": 900,
        },
        "inbound": None,
    },
    "custom_webhook": {
        "outbound": {
            "action_type": "post",
            "rate_limit_requests": 60,
            "rate_limit_window_seconds": 60,
        },
        "inbound": {
            "auth_method": "none",
            "destination_service": "tentackl",
        },
    },
}
