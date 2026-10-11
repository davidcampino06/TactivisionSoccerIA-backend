"""Generate the RSA key pair used to encrypt passwords in the browser.

    python scripts/generate_rsa_keys.py

Copy the printed RSA_PRIVATE_KEY line into the backend .env (local) or into
Render -> Environment (production). Never commit it. The public key is derived
from it and served by GET /api/auth/public-key.
"""

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def main() -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode("ascii")
    # One line with literal \n so it fits in a .env file or a Render variable.
    one_line = pem.strip().replace("\n", "\\n")
    print(f'RSA_PRIVATE_KEY="{one_line}"')


if __name__ == "__main__":
    main()
