#!/usr/bin/env python
"""
Seed default system templates for transactional emails.

These templates are platform-wide (organization_id=null) and serve as
defaults that organizations can override with their own branded versions.

Run with:
    docker compose exec mimic python scripts/seed_system_templates.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.database import SessionLocal
from src.database.models import SystemTemplate


# HTML email base template with styling
HTML_BASE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 40px 20px; }}
        .header {{ text-align: center; margin-bottom: 30px; }}
        .brand {{ font-size: 24px; font-weight: 600; color: #6366f1; }}
        .content {{ background: #ffffff; border-radius: 8px; padding: 30px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .button {{ display: inline-block; background: #6366f1; color: #ffffff; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 500; margin: 20px 0; }}
        .button:hover {{ background: #4f46e5; }}
        .code {{ font-size: 32px; font-weight: bold; letter-spacing: 4px; color: #6366f1; background: #f3f4f6; padding: 15px 25px; border-radius: 8px; display: inline-block; margin: 15px 0; }}
        .footer {{ text-align: center; margin-top: 30px; color: #6b7280; font-size: 14px; }}
        .warning {{ background: #fef3c7; border-left: 4px solid #f59e0b; padding: 15px; margin: 20px 0; border-radius: 0 8px 8px 0; }}
        h1 {{ margin: 0 0 20px 0; color: #111; }}
        p {{ margin: 0 0 15px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="brand">{{{{brand_name}}}}</div>
        </div>
        <div class="content">
            {content}
        </div>
        <div class="footer">
            {{{{footer_text}}}}
        </div>
    </div>
</body>
</html>"""


TEMPLATES = [
    {
        "name": "invitation",
        "subject": "You're invited to join {{organization_name}} on {{brand_name}}",
        "content_text": """You've Been Invited!

{{inviter_email}} has invited you to join {{organization_name}} on {{brand_name}}.

You've been assigned the role: {{role}}

Click the link below to accept the invitation and create your account:

{{invite_url}}

This invitation will expire in 7 days.

If you weren't expecting this invitation, you can safely ignore this email.

Best regards,
The {{brand_name}} Team
{{footer_text}}""",
        "content_html": HTML_BASE.format(content="""
            <h1>You've Been Invited!</h1>
            <p><strong>{{inviter_email}}</strong> has invited you to join <strong>{{organization_name}}</strong> on {{brand_name}}.</p>
            <p>You've been assigned the role: <strong>{{role}}</strong></p>
            <p style="text-align: center;">
                <a href="{{invite_url}}" class="button">Accept Invitation</a>
            </p>
            <p style="color: #6b7280; font-size: 14px;">This invitation will expire in 7 days.</p>
            <p style="color: #6b7280; font-size: 14px;">If you weren't expecting this invitation, you can safely ignore this email.</p>
        """),
        "variables": ["inviter_email", "organization_name", "invite_url", "role", "brand_name", "footer_text"],
    },
    {
        "name": "welcome",
        "subject": "Welcome to {{brand_name}}",
        "content_text": """Welcome to {{brand_name}}!

Your account has been created successfully.

Organization: {{organization_name}}
Email: {{email}}

You can now log in and start using {{brand_name}}.

Best regards,
The {{brand_name}} Team
{{footer_text}}""",
        "content_html": HTML_BASE.format(content="""
            <h1>Welcome to {{brand_name}}!</h1>
            <p>Your account has been created successfully.</p>
            <p><strong>Organization:</strong> {{organization_name}}</p>
            <p><strong>Email:</strong> {{email}}</p>
            <p>You can now log in and start using {{brand_name}}.</p>
        """),
        "variables": ["organization_name", "email", "brand_name", "footer_text"],
    },
    {
        "name": "password_reset",
        "subject": "Reset Your {{brand_name}} Password",
        "content_text": """Password Reset Request

You requested to reset your password. Use the following code to reset it:

Reset Code: {{otp_code}}

This code will expire in {{expires_minutes}} minutes.

If you didn't request this, please ignore this email or contact support if you have concerns.

Best regards,
The {{brand_name}} Team
{{footer_text}}""",
        "content_html": HTML_BASE.format(content="""
            <h1>Password Reset Request</h1>
            <p>You requested to reset your password. Use the following code to reset it:</p>
            <p style="text-align: center;">
                <span class="code">{{otp_code}}</span>
            </p>
            <p style="color: #6b7280; font-size: 14px;">This code will expire in {{expires_minutes}} minutes.</p>
            <div class="warning">
                <p style="margin: 0;"><strong>Didn't request this?</strong> Please ignore this email or contact support if you have concerns.</p>
            </div>
        """),
        "variables": ["otp_code", "expires_minutes", "brand_name", "footer_text"],
    },
    {
        "name": "password_changed",
        "subject": "Your {{brand_name}} Password Has Been Changed",
        "content_text": """Password Changed Successfully

Your password has been changed successfully.

If you didn't make this change, please contact support immediately and secure your account.

Best regards,
The {{brand_name}} Team
{{footer_text}}""",
        "content_html": HTML_BASE.format(content="""
            <h1>Password Changed Successfully</h1>
            <p>Your password has been changed successfully.</p>
            <div class="warning">
                <p style="margin: 0;"><strong>Didn't make this change?</strong> Please contact support immediately and secure your account.</p>
            </div>
        """),
        "variables": ["brand_name", "footer_text"],
    },
    {
        "name": "email_verification",
        "subject": "Verify Your {{brand_name}} Email",
        "content_text": """Verify Your Email Address

Welcome to {{brand_name}}! Please verify your email address by entering the following code:

Verification Code: {{otp_code}}

This code will expire in {{expires_minutes}} minutes.

If you didn't create an account with {{brand_name}}, please ignore this email.

Best regards,
The {{brand_name}} Team
{{footer_text}}""",
        "content_html": HTML_BASE.format(content="""
            <h1>Verify Your Email Address</h1>
            <p>Welcome to {{brand_name}}! Please verify your email address by entering the following code:</p>
            <p style="text-align: center;">
                <span class="code">{{otp_code}}</span>
            </p>
            <p style="color: #6b7280; font-size: 14px;">This code will expire in {{expires_minutes}} minutes.</p>
            <p style="color: #6b7280; font-size: 14px;">If you didn't create an account with {{brand_name}}, please ignore this email.</p>
        """),
        "variables": ["otp_code", "expires_minutes", "brand_name", "footer_text"],
    },
    {
        "name": "2fa_enabled",
        "subject": "{{brand_name}}: Two-Factor Authentication Enabled",
        "content_text": """Two-Factor Authentication Enabled

Two-factor authentication has been enabled on your {{brand_name}} account.

Your account is now more secure. You will need to enter a verification code from your authenticator app each time you log in.

Make sure to keep your backup codes in a safe place.

If you didn't enable this, please contact support immediately.

Best regards,
The {{brand_name}} Team
{{footer_text}}""",
        "content_html": HTML_BASE.format(content="""
            <h1>Two-Factor Authentication Enabled</h1>
            <p>Two-factor authentication has been enabled on your {{brand_name}} account.</p>
            <p>Your account is now more secure. You will need to enter a verification code from your authenticator app each time you log in.</p>
            <p><strong>Make sure to keep your backup codes in a safe place.</strong></p>
            <div class="warning">
                <p style="margin: 0;"><strong>Didn't enable this?</strong> Please contact support immediately.</p>
            </div>
        """),
        "variables": ["brand_name", "footer_text"],
    },
    {
        "name": "2fa_disabled",
        "subject": "{{brand_name}}: Two-Factor Authentication Disabled",
        "content_text": """Two-Factor Authentication Disabled

Two-factor authentication has been disabled on your {{brand_name}} account.

Your account now relies solely on your password for security. We recommend enabling 2FA for better protection.

If you didn't disable this, please contact support immediately and secure your account.

Best regards,
The {{brand_name}} Team
{{footer_text}}""",
        "content_html": HTML_BASE.format(content="""
            <h1>Two-Factor Authentication Disabled</h1>
            <p>Two-factor authentication has been disabled on your {{brand_name}} account.</p>
            <p>Your account now relies solely on your password for security. We recommend enabling 2FA for better protection.</p>
            <div class="warning">
                <p style="margin: 0;"><strong>Didn't disable this?</strong> Please contact support immediately and secure your account.</p>
            </div>
        """),
        "variables": ["brand_name", "footer_text"],
    },
    {
        "name": "login_alert",
        "subject": "{{brand_name}}: New Login Detected",
        "content_text": """New Login Detected

A new login to your {{brand_name}} account was detected.

IP Address: {{ip_address}}
Device: {{user_agent}}

If this was you, you can ignore this email.

If you didn't log in recently, please secure your account immediately by:
1. Changing your password
2. Enabling two-factor authentication
3. Reviewing your active sessions

Best regards,
The {{brand_name}} Team
{{footer_text}}""",
        "content_html": HTML_BASE.format(content="""
            <h1>New Login Detected</h1>
            <p>A new login to your {{brand_name}} account was detected.</p>
            <p><strong>IP Address:</strong> {{ip_address}}</p>
            <p><strong>Device:</strong> {{user_agent}}</p>
            <p style="color: #6b7280; font-size: 14px;">If this was you, you can ignore this email.</p>
            <div class="warning">
                <p style="margin: 0 0 10px 0;"><strong>Didn't log in recently?</strong> Please secure your account:</p>
                <ol style="margin: 0; padding-left: 20px;">
                    <li>Change your password</li>
                    <li>Enable two-factor authentication</li>
                    <li>Review your active sessions</li>
                </ol>
            </div>
        """),
        "variables": ["ip_address", "user_agent", "brand_name", "footer_text"],
    },
]


def seed_templates():
    """Seed default system templates."""
    db = SessionLocal()
    try:
        created = 0
        skipped = 0

        for template_data in TEMPLATES:
            # Check if template already exists
            existing = db.query(SystemTemplate).filter(
                SystemTemplate.name == template_data["name"],
                SystemTemplate.organization_id == None,  # Platform templates
            ).first()

            if existing:
                print(f"  Skipped: {template_data['name']} (already exists)")
                skipped += 1
                continue

            template = SystemTemplate(
                name=template_data["name"],
                subject=template_data["subject"],
                content_text=template_data["content_text"],
                content_html=template_data["content_html"],
                variables=template_data["variables"],
                organization_id=None,  # Platform-wide
            )
            db.add(template)
            created += 1
            print(f"  Created: {template_data['name']}")

        db.commit()
        print(f"\nSeeding complete: {created} created, {skipped} skipped")

    except Exception as e:
        db.rollback()
        print(f"Error seeding templates: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("Seeding system templates...")
    seed_templates()
