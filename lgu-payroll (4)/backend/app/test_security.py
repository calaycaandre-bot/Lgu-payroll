from .security import hash_pw, check_pw

def test_password_roundtrip():
    stored = hash_pw("Secret#123")
    assert check_pw("Secret#123", stored)
    assert not check_pw("wrong", stored)

def test_same_password_different_hash():
    assert hash_pw("abc12345") != hash_pw("abc12345")
