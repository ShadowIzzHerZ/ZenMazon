"""urlopen that trusts the macOS system keychain too. Homebrew Python's own CA file can lack a root the system trusts, which made every
HTTPS call (Supabase, Gemini, Groq) fail with CERTIFICATE_VERIFY_FAILED. Verification stays on."""
import ssl, subprocess, sys, time, urllib.error, urllib.request

_ctx = None


def _context():
    global _ctx
    if _ctx is None:
        _ctx = ssl.create_default_context()
        if sys.platform == "darwin":
            pem = subprocess.run(["security", "find-certificate", "-a", "-p", "/Library/Keychains/System.keychain",
                                  "/System/Library/Keychains/SystemRootCertificates.keychain"], capture_output=True, text=True).stdout
            if pem:
                _ctx.load_verify_locations(cadata=pem)
    return _ctx


def urlopen(req, timeout=30):
    """Retries connection-level failures (TLS or route errors before anything is sent). Supabase sits behind several Cloudflare addresses and
    on some networks one of them is flaky, so a retry lands on another. Timeouts and HTTP errors are never retried."""
    tries = 1 if req.full_url.startswith("http://") else 4
    for i in range(tries):
        try:
            return urllib.request.urlopen(req, timeout=timeout, context=_context())
        except urllib.error.HTTPError:
            raise
        except urllib.error.URLError as e:
            if isinstance(e.reason, TimeoutError) or i == tries - 1:
                raise
            time.sleep(0.25 * (i + 1))
