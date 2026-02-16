from cryptography.fernet import Fernet
import os

# Generate a key if not present (Not safe for production persistence across restarts without env var)
# In production, ENCRYPTION_KEY must be set in environment variables.
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", Fernet.generate_key().decode())

cipher_suite = Fernet(ENCRYPTION_KEY.encode())

def encrypt_value(value: str) -> str:
    """Encrypts a string value."""
    if not value:
        return None
    return cipher_suite.encrypt(value.encode()).decode()

def decrypt_value(token: str) -> str:
    """Decrypts a string token."""
    if not token:
        return None
    return cipher_suite.decrypt(token.encode()).decode()
