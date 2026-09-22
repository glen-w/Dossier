"""Launch the loopback workbench: ``python -m dossier.web``."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dossier.web", description="Dossier workbench")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args(argv)
    try:
        from dossier.web.app import serve
    except ImportError:
        print(
            "Workbench needs the [web] extra. Install with:\n"
            "  uv sync --extra web\n"
            "or:\n"
            "  uv pip install 'dossier[web]'",
            file=sys.stderr,
        )
        return 2
    if args.port < 1 or args.port > 65535:
        print("port must be 1-65535", file=sys.stderr)
        return 2
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print("workbench binds loopback only", file=sys.stderr)
        return 2
    print(f"http://{args.host}:{args.port}/")
    try:
        serve(host=args.host, port=args.port)
    except KeyboardInterrupt:
        print("\nstopped")
        return 0
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
