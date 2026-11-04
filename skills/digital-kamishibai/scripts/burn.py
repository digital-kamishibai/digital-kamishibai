"""Draw words on the screen into pictures with a headless browser (Microsoft Edge or Google Chrome).

Used by build_work.py. The drawing is done by burn.html with the room player's own code (player/js/overlay-dom.js)
and CSS (player/css/app.css), so what the narrator's draft shows and what listeners see come from the same hand.

Standard library only: a local HTTP server on 127.0.0.1 and a minimal WebSocket client for the browser's
DevTools protocol. Nothing leaves the computer.
"""
from __future__ import annotations

import base64
import http.server
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import quote, unquote

HERE = Path(__file__).resolve().parent
PLAYER = HERE.parents[2] / 'player'          # <repository>/player (the skill lives in <repository>/skills/...)
WIDTH, HEIGHT = 1920, 1080
JPEG_QUALITY = 92


class BurnError(Exception):
    pass


# ---------- finding a browser ----------

def find_browser() -> str | None:
    """DK_BROWSER, then Edge, then Chrome / Chromium in the usual places."""
    env = os.environ.get('DK_BROWSER')
    if env:
        return env if Path(env).is_file() or shutil.which(env) else None
    candidates = []
    if sys.platform == 'win32':
        for root in (os.environ.get('PROGRAMFILES(X86)'), os.environ.get('PROGRAMFILES'), os.environ.get('LOCALAPPDATA')):
            if root:
                candidates += [Path(root) / 'Microsoft/Edge/Application/msedge.exe',
                               Path(root) / 'Google/Chrome/Application/chrome.exe']
    elif sys.platform == 'darwin':
        candidates += [Path('/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'),
                       Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')]
    for c in candidates:
        if c.is_file():
            return str(c)
    for name in ('microsoft-edge', 'microsoft-edge-stable', 'google-chrome', 'google-chrome-stable', 'chromium',
                 'chromium-browser'):
        found = shutil.which(name)
        if found:
            return found
    return None


# ---------- local server ----------

class _Handler(http.server.SimpleHTTPRequestHandler):
    # The Windows registry sometimes maps .js to text/plain, and module scripts then refuse to load.
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html',
                      '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}
    roots: dict[str, Path] = {}

    def translate_path(self, path):
        path = unquote(path.split('?', 1)[0].split('#', 1)[0])
        for prefix, root in self.roots.items():
            if path.startswith(prefix):
                target = (root / path[len(prefix):]).resolve()
                if target == root or root in target.parents:
                    return str(target)
        return str(HERE / '__nothing__')

    def log_message(self, *args):
        pass


def _serve(media: Path):
    handler = type('Handler', (_Handler,), {'roots': {'/player/': PLAYER.resolve(), '/burn/': HERE,
                                                      '/media/': media.resolve()}})
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


# ---------- a minimal WebSocket client (RFC 6455, client side) ----------

class _WebSocket:
    def __init__(self, host: str, port: int, path: str):
        self.sock = socket.create_connection((host, port), timeout=60)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f'GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n'
                           f'Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
        head = b''
        while b'\r\n\r\n' not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise BurnError('the browser closed the DevTools connection')
            head += chunk
        if b' 101 ' not in head.split(b'\r\n', 1)[0]:
            raise BurnError('the browser refused the DevTools connection: ' + head.split(b'\r\n', 1)[0].decode(errors='replace'))
        self.buffer = head.split(b'\r\n\r\n', 1)[1]

    def _read(self, n: int) -> bytes:
        while len(self.buffer) < n:
            chunk = self.sock.recv(1 << 20)
            if not chunk:
                raise BurnError('the browser closed the DevTools connection')
            self.buffer += chunk
        data, self.buffer = self.buffer[:n], self.buffer[n:]
        return data

    def send(self, text: str) -> None:
        payload = text.encode()
        n = len(payload)
        header = bytes([0x81])
        if n < 126:
            header += bytes([0x80 | n])
        elif n < 65536:
            header += bytes([0x80 | 126]) + struct.pack('>H', n)
        else:
            header += bytes([0x80 | 127]) + struct.pack('>Q', n)
        mask = os.urandom(4)
        self.sock.sendall(header + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def recv(self) -> str:
        parts = []
        while True:
            b0, b1 = self._read(2)
            opcode, n = b0 & 0x0F, b1 & 0x7F
            if n == 126:
                n = struct.unpack('>H', self._read(2))[0]
            elif n == 127:
                n = struct.unpack('>Q', self._read(8))[0]
            if b1 & 0x80:
                mask = self._read(4)
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(self._read(n)))
            else:
                data = self._read(n)
            if opcode == 0x8:
                raise BurnError('the browser closed the DevTools connection')
            if opcode == 0x9:                      # ping → pong (masked, as a client must)
                mask = os.urandom(4)
                self.sock.sendall(bytes([0x8A, 0x80 | len(data)]) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))
                continue
            if opcode in (0x1, 0x2, 0x0):
                parts.append(data)
                if b0 & 0x80:
                    return b''.join(parts).decode()

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


# ---------- the browser ----------

class Browser:
    def __init__(self, executable: str):
        self.profile = Path(tempfile.mkdtemp(prefix='dk-burn-'))
        self.log = self.profile.with_name(self.profile.name + '.log')
        flags = ['--headless=new', '--remote-debugging-port=0', f'--user-data-dir={self.profile}',
                 '--remote-allow-origins=*', '--no-first-run', '--no-default-browser-check', '--hide-scrollbars',
                 '--force-device-scale-factor=1', '--disable-renderer-backgrounding',
                 '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows',
                 '--mute-audio']
        # Some Linux systems (containers, CI) forbid the browser's sandbox and it exits at once.
        # The page only loads files from 127.0.0.1, so turning the sandbox off there is an explicit opt-in.
        if os.environ.get('DK_BROWSER_NO_SANDBOX'):
            flags.append('--no-sandbox')
        with open(self.log, 'wb') as log:
            self.process = subprocess.Popen([executable, *flags, 'about:blank'], stdout=subprocess.DEVNULL, stderr=log)
        port_file = self.profile / 'DevToolsActivePort'
        for _ in range(600):                    # a first start on a fresh profile can be slow (CI, a new PC)
            try:
                if port_file.is_file() and len(port_file.read_text().split()) >= 2:
                    break
            except OSError:                     # Windows: the browser is still writing it (Permission denied)
                pass
            if self.process.poll() is not None:
                said = self.log.read_text(errors='replace').strip().splitlines()[-3:]
                hint = ('' if sys.platform != 'linux' or os.environ.get('DK_BROWSER_NO_SANDBOX')
                        else ' On Linux, try again with DK_BROWSER_NO_SANDBOX=1.')
                self.close()
                raise BurnError(f'the browser stopped at once ({executable}): {" / ".join(said)}.{hint}')
            time.sleep(0.1)
        else:
            self.close()
            raise BurnError('the browser did not open its DevTools port within 60 seconds')
        port, path = port_file.read_text().split()[:2]
        self.ws = _WebSocket('127.0.0.1', int(port), path)
        self.seq = 0
        target = self.call('Target.createTarget', {'url': 'about:blank'})['targetId']
        self.session = self.call('Target.attachToTarget', {'targetId': target, 'flatten': True})['sessionId']
        for method in ('Page.enable', 'Runtime.enable'):
            self.call(method, session=True)
        self.call('Emulation.setDeviceMetricsOverride',
                  {'width': WIDTH, 'height': HEIGHT, 'deviceScaleFactor': 1, 'mobile': False}, session=True)

    def call(self, method: str, params: dict | None = None, session: bool = False) -> dict:
        self.seq += 1
        message = {'id': self.seq, 'method': method, 'params': params or {}}
        if session:
            message['sessionId'] = self.session
        self.ws.send(json.dumps(message))
        while True:
            reply = json.loads(self.ws.recv())
            if reply.get('id') == self.seq:
                if 'error' in reply:
                    raise BurnError(f'{method}: {reply["error"].get("message")}')
                return reply.get('result', {})

    def evaluate(self, expression: str):
        r = self.call('Runtime.evaluate', {'expression': expression, 'awaitPromise': True, 'returnByValue': True},
                      session=True)
        if 'exceptionDetails' in r:
            details = r['exceptionDetails']
            text = (details.get('exception') or {}).get('description') or details.get('text')
            raise BurnError(f'the drawing page failed: {text}')
        return r['result'].get('value')

    def open(self, url: str) -> None:
        self.call('Page.navigate', {'url': url}, session=True)
        for _ in range(200):
            try:
                if self.evaluate('window.dkReady === true'):
                    return
            except BurnError:
                pass
            time.sleep(0.05)
        raise BurnError('the drawing page did not load (is player/ next to skills/ in the repository?)')

    def shoot(self, path: Path) -> None:
        data = self.call('Page.captureScreenshot',
                         {'format': 'jpeg', 'quality': JPEG_QUALITY,
                          'clip': {'x': 0, 'y': 0, 'width': WIDTH, 'height': HEIGHT, 'scale': 1}}, session=True)['data']
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(data))

    def close(self) -> None:
        if getattr(self, 'ws', None):
            self.ws.close()
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
        for _ in range(20):                     # the profile can stay locked for a moment on Windows
            shutil.rmtree(self.profile, ignore_errors=True)
            try:
                self.log.unlink(missing_ok=True)
            except OSError:
                pass
            if not self.profile.exists():
                break
            time.sleep(0.2)


# ---------- the job ----------

def render(jobs: list[dict], media: Path, executable: str) -> list[list[dict]]:
    """jobs: [{'picture': path relative to media or None, 'boxes': [{'box', 'words'}],
               'out': Path, 'base': Path or None}]. Writes 'out' (with words) and 'base' (without) as JPEG.
    Returns, per job and per box, {'off': runs off the slide, 'outside': runs out of its colour band}."""
    if not (PLAYER / 'js' / 'overlay-dom.js').is_file():
        raise BurnError(f'the room player is not found at {PLAYER}; drawing words needs the whole repository')
    server = _serve(media)
    browser = None
    fits = []
    try:
        browser = Browser(executable)
        browser.open(f'http://127.0.0.1:{server.server_address[1]}/burn/burn.html')
        for job in jobs:
            picture = (f'/media/{quote(job["picture"])}' if job['picture'] else None)
            for boxes, out in ((job['boxes'], job['out']), ([], job.get('base'))):
                if out is None:
                    continue
                fit = browser.evaluate(f'window.dkRender({json.dumps({"picture": picture, "boxes": boxes})})')
                if boxes:
                    fits.append(fit)
                browser.shoot(out)
        return fits
    finally:
        if browser:
            browser.close()
        server.shutdown()
        server.server_close()
