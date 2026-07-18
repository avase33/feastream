"""feastream-infer CLI: `demo`, `serve`, `eval`."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(prog="feastream-infer")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo", help="train and score example vectors")
    p_serve = sub.add_parser("serve", help="run the FastAPI inference server")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)
    sub.add_parser("eval", help="train and report holdout accuracy / AUC")

    args = parser.parse_args(argv)

    if args.cmd == "demo":
        from .demo import run

        run()
        return 0

    if args.cmd == "eval":
        from .evaluate import run as run_eval

        run_eval()
        return 0

    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("feastream_infer.service:app", host=args.host, port=args.port)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
