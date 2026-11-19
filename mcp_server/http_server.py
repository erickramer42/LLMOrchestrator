"""The server over Streamable HTTP (ADR-0004): bearer tokens on every
request, DNS rebinding protection always on, refused requests audited.

It binds to loopback unless told otherwise; another host needs TLS or an
explicit --insecure-http, and the server refuses to start without tokens.
"""

import ipaddress
import os
from dataclasses import dataclass
from typing import List, Optional

from mcp.server.transport_security import TransportSecuritySettings

from mcp_server.guard import HttpRefusals
from mcp_server.server import Settings, build_server
from mcp_server.tokens import TokenStore

LOOPBACK_NAMES = ("localhost",)


@dataclass(frozen=True)
class HttpOptions:
    host: str = "127.0.0.1"
    port: int = 8765
    certfile: Optional[str] = None
    keyfile: Optional[str] = None
    insecure_http: bool = False


def is_loopback(host: str) -> bool:
    if host in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _env_list(name: str) -> List[str]:
    return [v.strip() for v in (os.environ.get(name) or "").split(",") if v.strip()]


def check_options(opts: HttpOptions, settings: Settings) -> None:
    """Refuse a configuration that would serve without protection."""
    if bool(opts.certfile) != bool(opts.keyfile):
        raise ValueError("--certfile and --keyfile go together")
    if not is_loopback(opts.host) and not opts.certfile and not opts.insecure_http:
        raise ValueError(f"{opts.host} is not a loopback address: serve it with --certfile "
                         "and --keyfile, or pass --insecure-http to send tokens in clear text")
    if not TokenStore(settings.tokens_path).entries():
        raise ValueError(f"no tokens in {settings.tokens_path}: add one with "
                         "python -m mcp_server token add <id> --scope review")


def security_settings(opts: HttpOptions) -> TransportSecuritySettings:
    """Host and Origin checks for this binding, plus LLMORCH_ALLOWED_HOSTS
    and LLMORCH_ALLOWED_ORIGINS. A request without an Origin passes."""
    hosts = [f"{opts.host}:{opts.port}"]
    origins = []
    if is_loopback(opts.host):
        hosts += [f"127.0.0.1:{opts.port}", f"localhost:{opts.port}", f"[::1]:{opts.port}"]
        origins += [f"http://127.0.0.1:{opts.port}", f"http://localhost:{opts.port}"]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=sorted(set(hosts + _env_list("LLMORCH_ALLOWED_HOSTS"))),
        allowed_origins=sorted(set(origins + _env_list("LLMORCH_ALLOWED_ORIGINS"))))


def build_app(opts: HttpOptions, settings: Optional[Settings] = None, queue=None, limiter=None):
    """The ASGI app: the MCP endpoint at /mcp behind the token check, wrapped
    to audit refused requests. Returns (app, server)."""
    settings = settings or Settings.from_env()
    check_options(opts, settings)
    scheme = "https" if opts.certfile else "http"
    server = build_server(settings, queue, transport="http",
                          base_url=f"{scheme}://{opts.host}:{opts.port}", limiter=limiter)
    app = server.streamable_http_app(host=opts.host, transport_security=security_settings(opts))
    return HttpRefusals(app, server.guard.audit), server


def serve(opts: HttpOptions) -> None:
    import uvicorn

    app, _ = build_app(opts)
    uvicorn.run(app, host=opts.host, port=opts.port, ssl_certfile=opts.certfile,
                ssl_keyfile=opts.keyfile, access_log=False, log_level="warning")
