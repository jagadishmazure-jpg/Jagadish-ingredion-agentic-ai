"""Mint a demo bearer token for the agent service.

Usage:
    python -m ingredion_ai.service.mint_token \\
        --subject demo-client \\
        --scopes formulation:write,supply:read,esg:read,proposal:read

Then call the service, e.g.::

    curl -s -X POST http://localhost:8000/api/reformulate \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"scenario": "sweet_bakery_cake"}'

Demo only: tokens are the synthetic JWT-shaped tokens from
:mod:`ingredion_ai.interop.auth` (HMAC dev key, NOT a secret). In
production the service validates Entra ID tokens instead — see
``docs/identity.md``.
"""

from __future__ import annotations

import argparse

from ingredion_ai.interop.auth import DEMO_ISSUER, issue_token


def main(argv: list | None = None) -> str:
    parser = argparse.ArgumentParser(description="Mint a demo bearer token")
    parser.add_argument("--subject", default="demo-client")
    parser.add_argument(
        "--scopes",
        default="formulation:write,supply:read,esg:read,proposal:read",
        help="Comma-separated scopes",
    )
    parser.add_argument("--ttl", type=int, default=3600, help="Seconds until expiry")
    args = parser.parse_args(argv)
    scopes = [s.strip() for s in args.scopes.split(",") if s.strip()]
    token = issue_token(args.subject, scopes, ttl_seconds=args.ttl)
    print(f"# issuer: {DEMO_ISSUER} | subject: {args.subject} | scopes: {','.join(scopes)}")
    print(token)
    return token


if __name__ == "__main__":
    main()
