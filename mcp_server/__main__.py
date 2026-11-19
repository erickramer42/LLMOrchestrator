"""Run the MCP server, or manage its HTTP tokens.

    python -m mcp_server                                  stdio (what a client starts)
    python -m mcp_server --http [--host H] [--port P] [--certfile F --keyfile F] [--insecure-http]
    python -m mcp_server token add <id> --scope review [--scope read]
    python -m mcp_server token list
    python -m mcp_server token revoke <id>

From any directory, `python <repo>/mcp_server` works the same.
"""

import argparse
import sys
from pathlib import Path

# The core modules sit at the repo root, which a client's working directory
# need not be. Run as a folder, this package's own folder heads the path,
# where its modules would shadow libraries of the same name.
_PACKAGE = Path(__file__).resolve().parent
sys.path[:] = [p for p in sys.path if p and Path(p).resolve() != _PACKAGE]
sys.path.insert(0, str(_PACKAGE.parent))

from mcp_server.tokens import SCOPES  # noqa: E402


def token_command(args) -> int:
    from mcp_server.server import Settings
    from mcp_server.tokens import TokenStore

    store = TokenStore(Settings.from_env().tokens_path)
    if args.action == "add":
        try:
            token = store.add(args.id, args.scope or [])
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"Token for {args.id} ({', '.join(sorted(set(args.scope)))}); it is shown once "
              f"and stored only as a hash in {store.path}:")
        print(token)
        return 0
    if args.action == "list":
        for e in store.entries():
            print(f"{e['id']}\t{','.join(e.get('scopes', []))}\t{e.get('created_utc', '')}")
        return 0
    if store.revoke(args.id):
        print(f"Revoked {args.id}")
        return 0
    print(f"error: no token named {args.id!r}", file=sys.stderr)
    return 1


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["token"]:
        parser = argparse.ArgumentParser(prog="python -m mcp_server token")
        sub = parser.add_subparsers(dest="action", required=True)
        add = sub.add_parser("add")
        add.add_argument("id")
        add.add_argument("--scope", action="append", choices=SCOPES, required=True)
        sub.add_parser("list")
        rev = sub.add_parser("revoke")
        rev.add_argument("id")
        return token_command(parser.parse_args(argv[1:]))

    parser = argparse.ArgumentParser(prog="python -m mcp_server")
    parser.add_argument("--http", action="store_true", help="serve Streamable HTTP, not stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--certfile")
    parser.add_argument("--keyfile")
    parser.add_argument("--insecure-http", action="store_true",
                        help="allow a non-loopback host without TLS")
    args = parser.parse_args(argv)
    if not args.http:
        from mcp_server.server import build_server
        build_server().run("stdio")
        return 0
    from mcp_server.http_server import HttpOptions, serve
    try:
        serve(HttpOptions(args.host, args.port, args.certfile, args.keyfile, args.insecure_http))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
