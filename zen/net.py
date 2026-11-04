"""urlopen that trusts the macOS system keychain too. Homebrew Python's own CA file can lack a root the system trusts, which made every
HTTPS call (Supabase, Gemini, Groq) fail with CERTIFICATE_VERIFY_FAILED. Verification stays on."""
import ssl, subprocess, sys, urllib.request

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
    return urllib.request.urlopen(req, timeout=timeout, context=_context())
