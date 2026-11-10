"""Generate an HMAC signature for the EXACT JSON body sent in Insomnia.

Example:
    python scripts/sign_callback.py callback.json

The secret is loaded from PAYMENT_CALLBACK_SECRET in your environment.
Alternatively use --secret to pass a local development secret.
"""
import argparse
import hashlib
import hmac
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("body_file", type=Path)
    parser.add_argument("--secret", default=os.getenv("PAYMENT_CALLBACK_SECRET"))
    args = parser.parse_args()
    if not args.secret:
        parser.error("Set PAYMENT_CALLBACK_SECRET or provide --secret")
    raw = args.body_file.read_bytes()
    signature = hmac.new(args.secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    print("X-Callback-Signature: sha256=" + signature)
    print("IMPORTANT: Send the exact raw contents of the file as request body.")


if __name__ == "__main__":
    main()
