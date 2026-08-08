"""
Validators module for AutoSINAPI API.
Includes anti-disposable email checking, CPF/CNPJ validation (LGPD & KYC compliance).
"""
import re
from typing import Set

# Curated list of known temporary/disposable email domains
DISPOSABLE_EMAIL_DOMAINS: Set[str] = {
    "10minutemail.com",
    "guerrillamail.com",
    "mailinator.com",
    "tempmail.com",
    "trashmail.com",
    "sharklasers.com",
    "getnada.com",
    "throwawaymail.com",
    "yopmail.com",
    "temp-mail.org",
}

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_email(email: str) -> bool:
    """Validate email syntax and check against disposable domains list."""
    if not email or not isinstance(email, str):
        return False
    
    email = email.strip().lower()
    if not EMAIL_REGEX.match(email):
        return False
    
    domain = email.split("@")[-1]
    if domain in DISPOSABLE_EMAIL_DOMAINS:
        return False
    
    return True


def validate_cpf(cpf: str) -> bool:
    """Basic CPF validation (digits and formatting)."""
    if not cpf or not isinstance(cpf, str):
        return False
    digits = re.sub(r"\D", "", cpf)
    if len(digits) != 11:
        return False
    # Check for known invalid CPFs (all digits equal)
    if digits == digits[0] * 11:
        return False
    return True


def validate_cnpj(cnpj: str) -> bool:
    """Basic CNPJ validation (digits and formatting)."""
    if not cnpj or not isinstance(cnpj, str):
        return False
    digits = re.sub(r"\D", "", cnpj)
    if len(digits) != 14:
        return False
    if digits == digits[0] * 14:
        return False
    return True
