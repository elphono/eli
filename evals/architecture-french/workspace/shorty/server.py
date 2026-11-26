"""The HTTP side: POST /shorten makes a short link, GET /<code> redirects to its target."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from shorty import codes, config, stats, store


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/shorten":
            return self.send_error(404)
        url = self.rfile.read(int(self.headers["Content-Length"])).decode()
        code = codes.new_code()
        store.save(code, url)
        self.send_response(201)
        self.end_headers()
        self.wfile.write(f"/{code}".encode())

    def do_GET(self):
        code = self.path.lstrip("/")
        url = store.find(code) if codes.is_valid(code) else None
        if url is None:
            return self.send_error(404)
        stats.record(code)
        self.send_response(302)
        self.send_header("Location", url)
        self.end_headers()


if __name__ == "__main__":
    ThreadingHTTPServer(("", config.PORT), Handler).serve_forever()
