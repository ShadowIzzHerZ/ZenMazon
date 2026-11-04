"""urlopen that trusts the macOS system keychain too. Homebrew Python's own CA file can lack a root the system trusts, which made every
HTTPS call (Supabase, Gemini, Groq) fail with CERTIFICATE_VERIFY_FAILED. Verification stays on."""
import http.client, random, socket, ssl, subprocess, sys, time, urllib.error, urllib.request

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


class _Conn(http.client.HTTPSConnection):
    """Tries every address a host resolves to, in random order, and moves on when one fails to connect or to verify. On some networks one
    of a CDN's addresses is blocked or presents the wrong certificate, and the default connector would keep hitting it."""
    def connect(self):
        infos = socket.getaddrinfo(self.host, self.port, 0, socket.SOCK_STREAM)
        random.shuffle(infos)
        last = OSError("no address")
        for fam, typ, proto, _, addr in infos:
            sock = None
            try:
                sock = socket.socket(fam, typ, proto)
                sock.settimeout(self.timeout)
                sock.connect(addr)
                self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
                return
            except OSError as e:
                last = e
                if sock:
                    sock.close()
        raise last


class _Handler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_Conn, req, context=self._context)


_opener = None


def urlopen(req, timeout=30):
    """Retries connection-level failures (TLS or route errors before anything is sent). Timeouts and HTTP errors are never retried."""
    global _opener
    if _opener is None:
        _opener = urllib.request.build_opener(_Handler(context=_context()))
    tries = 1 if req.full_url.startswith("http://") else 4
    for i in range(tries):
        try:
            return _opener.open(req, timeout=timeout)
        except urllib.error.HTTPError:
            raise
        except urllib.error.URLError as e:
            if isinstance(e.reason, TimeoutError) or i == tries - 1:
                raise
            time.sleep(0.25 * (i + 1))
