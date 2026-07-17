import argparse
import ipaddress
import os
import sys


def _run_desktop():
    from ui.main_window import initialize_ui
    initialize_ui()


def _is_loopback_host(host: str) -> bool:
    """True when the bind address can only be reached from this machine."""
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def check_web_tls(host: str, certfile: str, keyfile: str,
                  behind_proxy: bool, allow_insecure: bool) -> str:
    """Validate the TLS configuration for the web server.

    Returns one of "tls", "loopback", "behind-proxy", or "insecure".
    Raises SystemExit with an actionable message when the configuration
    would expose HTTP Basic Auth credentials in cleartext on the network.
    """
    if bool(certfile) != bool(keyfile):
        raise SystemExit(
            "Error: --ssl-certfile and --ssl-keyfile must be given together."
        )
    if certfile:
        for label, path in (("certificate", certfile), ("private key", keyfile)):
            if not os.path.isfile(path):
                raise SystemExit(f"Error: TLS {label} file not found: {path}")
        return "tls"
    if _is_loopback_host(host):
        return "loopback"
    if behind_proxy:
        return "behind-proxy"
    if allow_insecure:
        return "insecure"
    raise SystemExit(
        f"Error: refusing to serve plain HTTP on non-loopback address {host!r}.\n"
        "RadSpeed uses HTTP Basic Auth, which sends credentials (and PHI) in\n"
        "cleartext without TLS. Choose one of:\n"
        "  1. Terminate TLS in-app:   --ssl-certfile cert.pem --ssl-keyfile key.pem\n"
        "     (or set RADSPEED_SSL_CERTFILE / RADSPEED_SSL_KEYFILE)\n"
        "  2. TLS terminated upstream (nginx / Fly.io / Render / other reverse\n"
        "     proxy): set RADSPEED_BEHIND_PROXY=1\n"
        "  3. Local-only use:         --host 127.0.0.1\n"
        "  4. I understand the risk:  --insecure "
        "(or RADSPEED_ALLOW_INSECURE_HTTP=1)\n"
        "See docs/deploy-web.md for details."
    )


def _run_web(host: str, port: int, certfile: str = "", keyfile: str = "",
             behind_proxy: bool = False, allow_insecure: bool = False):
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    log = logging.getLogger(__name__)

    certfile = certfile or os.environ.get("RADSPEED_SSL_CERTFILE", "")
    keyfile = keyfile or os.environ.get("RADSPEED_SSL_KEYFILE", "")
    behind_proxy = behind_proxy or _env_flag("RADSPEED_BEHIND_PROXY")
    allow_insecure = allow_insecure or _env_flag("RADSPEED_ALLOW_INSECURE_HTTP")

    mode = check_web_tls(host, certfile, keyfile, behind_proxy, allow_insecure)
    if mode == "insecure":
        log.warning(
            "Serving plain HTTP on %s — Basic Auth credentials and report "
            "content are visible to anyone on the network path. Use TLS for "
            "any real deployment (see docs/deploy-web.md).", host,
        )
    # Let web.app (imported below) see the effective TLS state so it can mark
    # session cookies Secure when the browser-facing scheme is HTTPS.
    if mode == "tls":
        os.environ["RADSPEED_SSL_CERTFILE"] = certfile
        os.environ["RADSPEED_SSL_KEYFILE"] = keyfile

    from config.settings import load_settings
    load_settings(web_mode=True)

    if os.environ.get("VOXRAD_MOCK_MODE"):
        log.info(
            "[mock] Mock mode active — transcribe and format return canned responses"
        )

    import uvicorn
    from web.app import app as web_app

    scheme = "https" if mode == "tls" else "http"
    url = f"{scheme}://{'localhost' if host == '0.0.0.0' else host}:{port}/"
    print(f"\n  RadSpeed web server → {url}\n")
    uvicorn.run(
        web_app, host=host, port=port, log_level="info",
        ssl_certfile=certfile or None,
        ssl_keyfile=keyfile or None,
    )


def main():
    parser = argparse.ArgumentParser(description="RadSpeed — AI-assisted radiology reporting")
    parser.add_argument(
        "--web", action="store_true",
        help="Launch web server instead of the desktop UI"
    )
    parser.add_argument(
        "--host", default="0.0.0.0",
        help="Web server bind address (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=8765,
        help="Web server port (default: 8765)"
    )
    parser.add_argument(
        "--ssl-certfile", default="",
        help="TLS certificate (PEM) — serve HTTPS directly from the app "
             "(env: RADSPEED_SSL_CERTFILE)"
    )
    parser.add_argument(
        "--ssl-keyfile", default="",
        help="TLS private key (PEM) — required with --ssl-certfile "
             "(env: RADSPEED_SSL_KEYFILE)"
    )
    parser.add_argument(
        "--behind-proxy", action="store_true",
        help="TLS is terminated by an upstream reverse proxy "
             "(env: RADSPEED_BEHIND_PROXY=1)"
    )
    parser.add_argument(
        "--insecure", action="store_true",
        help="Allow plain HTTP on a non-loopback address — credentials are "
             "sent in cleartext (env: RADSPEED_ALLOW_INSECURE_HTTP=1)"
    )
    args = parser.parse_args()

    if args.web:
        _run_web(
            args.host, args.port,
            certfile=args.ssl_certfile, keyfile=args.ssl_keyfile,
            behind_proxy=args.behind_proxy, allow_insecure=args.insecure,
        )
    else:
        _run_desktop()


if __name__ == "__main__":
    main()
