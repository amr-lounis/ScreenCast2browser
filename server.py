"""Flask server: MJPEG streaming + heartbeat + auth."""
import logging
import threading
import time
import secrets
import socket
from typing import Any, Generator, List

from flask import Flask, Response, request, abort, jsonify
import config
from capture import generate

logger = logging.getLogger(__name__)

app = Flask(__name__)

# Rate-limit: 10 failed attempts per 60s per IP
_RATE_LIMIT_MAX: int = 10
_RATE_LIMIT_WINDOW: int = 60

# Max concurrent /video viewers (0 = unlimited)
MAX_CLIENTS: int = 1

_active_streams: int = 0
_streams_lock = threading.Lock()


def _try_acquire_stream() -> bool:
    global _active_streams
    with _streams_lock:
        if 0 < MAX_CLIENTS <= _active_streams:
            return False
        _active_streams += 1
        return True


def _release_stream() -> None:
    global _active_streams
    with _streams_lock:
        _active_streams = max(0, _active_streams - 1)


def _counted_generate() -> Generator[bytes, None, None]:
    try:
        yield from generate()
    finally:
        _release_stream()


def _recent_attempts(ip: str, now: float) -> List[float]:
    with config._rate_limit_lock:
        lst = [t for t in config._rate_limit.get(ip, []) if now - t < _RATE_LIMIT_WINDOW]
        config._rate_limit[ip] = lst
        return lst


def _is_rate_limited(ip: str) -> bool:
    return len(_recent_attempts(ip, time.time())) >= _RATE_LIMIT_MAX


def _record_failed(ip: str) -> None:
    now = time.time()
    lst = _recent_attempts(ip, now)
    lst.append(now)


def is_authorized(req: Any) -> bool:
    """Check access code - timing-safe, supports header and query"""
    code_required: str = config.config.get("access_code", "")
    if not code_required:
        return True
    provided: str = req.args.get("code", "")
    if not provided:
        provided = req.headers.get("X-Access-Code", "")
    try:
        ok = secrets.compare_digest(provided, code_required)
    except Exception:
        ok = (provided == code_required)
    if not ok:
        ip: str = req.remote_addr or "unknown"
        if _is_rate_limited(ip):
            logger.warning("Rate limit hit for %s", ip)
            abort(429, description="Too many failed attempts")
        _record_failed(ip)
        logger.info("Auth failed for %s", ip)
    return ok


# Frozen-frame client: main <img> is never cleared, so on disconnect the last
# frame stays visible (no black flash, no badge). Reconnects go through a
# hidden probe image; img.src swaps only once the new stream delivers data.
INDEX_HTML = '''<html><head><title>ScreenCast->browser</title><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<style>html,body{margin:0;height:100%;background:#000}img{width:100%;height:100%;object-fit:contain}</style>
</head>
<body>
<img id="s" alt="">
<script>
// --- setup ---
const code=new URLSearchParams(location.search).get('code')||'';
const img=document.getElementById('s');
const vurl=()=>'/video'+(code?'?code='+encodeURIComponent(code):'');
const surl=()=>'/status'+(code?'?code='+encodeURIComponent(code):'');
const fresh=(b)=>b+(b.includes('?')?'&':'?')+'t='+Date.now();

// --- state ---
let gen=-1, lastId=-1, lastOk=Date.now(), delay=700, busy=false;
let retryTimer=null;

// --- silent retry with backoff ---
function retry(){
  const d=delay;
  delay=Math.min(delay*1.6,8000);
  clearTimeout(retryTimer);
  retryTimer=setTimeout(connect,d);
}

// --- connect via hidden probe: swap only when stream is alive ---
function connect(){
  if(busy) return;
  busy=true;
  const probe=new Image();
  probe.onload=()=>{ img.src=probe.src; busy=false; delay=700; lastOk=Date.now(); };
  probe.onerror=()=>{ busy=false; retry(); };
  probe.src=fresh(vurl());
}

// --- heartbeat: is the server producing new frames? ---
async function check(){
  if(document.hidden) return;
  try{
    const r=await fetch(surl(),{cache:'no-store'});
    if(!r.ok) throw new Error('http '+r.status);
    const d=await r.json();
    const now=Date.now();
    if(gen===-1){ gen=d.generation; lastId=d.frame_id; lastOk=now; delay=700; return; }
    if(d.generation!==gen){ gen=d.generation; lastId=d.frame_id; lastOk=now; delay=700; connect(); return; }
    if(d.frame_id!==lastId){ lastId=d.frame_id; lastOk=now; delay=700; }
    else if(now-lastOk>2500 && !busy){ lastOk=now; connect(); }
  }catch(e){ retry(); }
}

// --- stream broke: keep last frame, retry silently ---
img.onerror=()=>{ if(!busy) retry(); };

// --- run ---
connect();
const statusTimer=setInterval(check,1000);
document.addEventListener('visibilitychange',()=>{ if(!document.hidden) check(); });
window.addEventListener('beforeunload',()=>{ clearInterval(statusTimer); clearTimeout(retryTimer); });
</script>
</body></html>'''


@app.route('/')
def index() -> str:
    return INDEX_HTML


@app.route('/ping')
def ping() -> Any:
    if not is_authorized(request):
        abort(403)
    return 'ok', 200


@app.route('/status')
def status() -> Any:
    """Heartbeat: frame counter + stream generation for stall/restart detection."""
    if not is_authorized(request):
        abort(403)
    with config.lock:
        fid = int(config.frame_id)
        gen = int(config.stream_generation)
        fps = int(config.config.get("fps", 0))
    running = not config.stop_event.is_set()
    resp = jsonify({"frame_id": fid, "generation": gen, "fps": fps, "running": running})
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


@app.route('/video')
def video() -> Any:
    if not is_authorized(request):
        abort(403, description="Invalid access code")
    if not _try_acquire_stream():
        logger.info("Rejected /video from %s: max clients (%d) reached", request.remote_addr, MAX_CLIENTS)
        abort(429, description="Server busy: max clients reached")
    with config.lock:
        gen = int(config.stream_generation)
    resp = Response(_counted_generate(), mimetype='multipart/x-mixed-replace; boundary=frame')
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    # Critical for restart: force close so browser doesn't reuse stale keep-alive socket
    resp.headers['Connection'] = 'close'
    resp.headers['X-Accel-Buffering'] = 'no'
    resp.headers['X-Stream-Generation'] = str(gen)
    return resp


def _check_port_available(port: int) -> None:
    """Pre-check if port is free (SO_REUSEADDR=0) to detect busy port reliably."""
    if port == 0:
        return
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        except Exception:
            pass
        s.bind(('0.0.0.0', port))


def _clear_server(srv: Any) -> None:
    with config.server_lock:
        if config.server is srv:
            config.server = None


def run_server(port: int) -> None:
    """Run Flask/Werkzeug server - thread-safe, preserves existing server on bind failure."""
    logger.info("Starting server on port %d (werkzeug=%s)", port, config.HAS_WERKZEUG)
    try:
        _check_port_available(port)
        if config.HAS_WERKZEUG:
            srv = config.make_server('0.0.0.0', port, app, threaded=True)  # type: ignore
            with config.server_lock:
                config.server = srv
            try:
                logger.info("Werkzeug server serving on 0.0.0.0:%d", port)
                srv.serve_forever()
            finally:
                _clear_server(srv)
                logger.info("Werkzeug server stopped")
        else:
            with config.server_lock:
                config.server = app
            try:
                logger.info("Flask dev server on 0.0.0.0:%d", port)
                app.run(host='0.0.0.0', port=port, threaded=True, use_reloader=False)
            finally:
                _clear_server(app)
                logger.info("Flask dev server stopped")
    except OSError as e:
        logger.error("Failed to bind port %d: %s", port, e)
        raise
    except Exception as e:
        logger.exception("Server unexpected error on port %d: %s", port, e)
        raise
