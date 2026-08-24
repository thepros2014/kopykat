"""Container/process entry point with validated port configuration."""

from __future__ import annotations

import os

import uvicorn


def _port() -> int:
    try:
        port = int(os.getenv("PORT", "10000"))
    except ValueError as exc:
        raise SystemExit("PORT must be an integer between 1 and 65535") from exc
    if not 1 <= port <= 65535:
        raise SystemExit("PORT must be an integer between 1 and 65535")
    return port


def main() -> None:
    # Keep one application process by default because APScheduler is owned by
    # the web process. Scale with multiple service instances or a dedicated
    # worker when the deployment needs more throughput.
    uvicorn.run(
        "server.main:app",
        # Containers must listen on all interfaces; the platform firewall and
        # proxy are the external boundary.  Keep the bind address configurable.
        host=os.getenv("HOST", "0.0.0.0"),  # nosec B104 - intentional container bind
        port=_port(),
        workers=1,
        proxy_headers=True,
        forwarded_allow_ips=os.getenv("TRUSTED_PROXIES", "127.0.0.1"),
    )


if __name__ == "__main__":
    main()
