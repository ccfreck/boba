import argparse
import asyncio
import logging
from pathlib import Path

from boba.gateway.server import serve


def main() -> None:
    parser = argparse.ArgumentParser(description="Boba — your AI agent's security bouncer")
    parser.add_argument("--config", type=Path, default=Path("config/boba.yaml"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    # SDK diagnostic exceptions can embed untrusted payloads.
    logging.getLogger("mcp").disabled = True
    logging.getLogger("mcp").addHandler(logging.NullHandler())
    logging.getLogger("mcp").propagate = False
    try:
        asyncio.run(serve(args.config))
    except KeyboardInterrupt:
        pass
    except Exception:
        logging.error("Boba stopped: configuration, storage, or downstream initialization failed")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
