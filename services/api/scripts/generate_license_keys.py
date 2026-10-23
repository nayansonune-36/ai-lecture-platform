"""Generate Ed25519 keypair for offline license signing."""

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def generate_license_keypair() -> tuple[str, str]:
    """Generate Ed25519 private and public keys in PEM format."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    return private_pem, public_pem


def main() -> None:
    priv_pem, pub_pem = generate_license_keypair()
    single_line_priv = priv_pem.replace("\n", "\\n")

    print("=================================================================")
    print("AI Lecture Platform - Ed25519 License Signing Key Generator")
    print("=================================================================\n")
    print("Add this line to your .env file:\n")
    print(f'LICENSE_SIGNING_KEY="{single_line_priv}"\n')
    print("-----------------------------------------------------------------")
    print("Public Key (distributed to clients / returned via /license-public-key):\n")
    print(pub_pem)
    print("=================================================================")


if __name__ == "__main__":
    main()
