import http.server
import socketserver
import sys

class SecureHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        # First use the base class to resolve the path securely within CWD.
        translated = super().translate_path(path)
        return translated

    def _is_allowed(self):
        translated = self.translate_path(self.path)
        # We only want to serve data.out
        if not translated.endswith('data.out'):
            self.send_error(403, "Forbidden.")
            return False
        return True

    def do_GET(self):
        if self._is_allowed():
            super().do_GET()

    def do_HEAD(self):
        if self._is_allowed():
            super().do_HEAD()

class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 57275

    handler = SecureHTTPRequestHandler

    with ReusableTCPServer(("", port), handler) as httpd:
        print(f"Serving at port {port}")
        print("Note: Only data.out will be served.")
        httpd.serve_forever()

if __name__ == "__main__":
    main()
