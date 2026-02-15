"""Two-Factor Authentication utilities"""

import pyotp
import qrcode
import io
import base64
from typing import Tuple


def generate_2fa_secret() -> str:
    """Generate a new TOTP secret"""
    return pyotp.random_base32()


def get_2fa_uri(secret: str, email: str, issuer: str = "inkPass") -> str:
    """Get the provisioning URI for QR code generation"""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=issuer)


def generate_qr_code(uri: str) -> str:
    """Generate a QR code image as base64 string"""
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(uri)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    img_str = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"


def verify_2fa_code(secret: str, code: str) -> bool:
    """Verify a 2FA code"""
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


def generate_backup_codes(count: int = 10) -> list[str]:
    """Generate backup codes for 2FA"""
    import secrets
    codes = []
    for _ in range(count):
        code = secrets.token_hex(4).upper()
        codes.append(f"{code[:4]}-{code[4:]}")
    return codes


