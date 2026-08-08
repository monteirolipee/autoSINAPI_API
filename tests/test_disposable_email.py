"""
TDD tests for anti-disposable email validator and KYC validators (CPF/CNPJ).
"""
import pytest
from api.validators import validate_email, validate_cpf, validate_cnpj


def test_validate_email_valid():
    assert validate_email("user@example.com") is True
    assert validate_email("engenheiro.civil@mundoaec.com.br") is True


def test_validate_email_disposable():
    assert validate_email("test@10minutemail.com") is False
    assert validate_email("spam@yopmail.com") is False
    assert validate_email("anon@mailinator.com") is False


def test_validate_email_invalid_syntax():
    assert validate_email("invalid-email") is False
    assert validate_email("@no-user.com") is False
    assert validate_email(None) is False


def test_validate_cpf():
    assert validate_cpf("12345678909") is True or validate_cpf("123.456.789-09") is True
    assert validate_cpf("11111111111") is False
    assert validate_cpf("123") is False


def test_validate_cnpj():
    assert validate_cnpj("12345678000199") is True
    assert validate_cnpj("00000000000000") is False
    assert validate_cnpj("123") is False
