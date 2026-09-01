"""
server.py - Flask server and streaming (Phase 4: fixed restart stutter)
"""
import logging
import time
import secrets
import socket
from typing import Any

from flask import Flask, Response, request, abort
import config
from capture import generate

logger = logging.getLogger(__name__)

app = Flask(__name__)

# Rate-limit: 10 failed attempts per 60s per IP
_RATE_LIMIT_MAX: int = 10
_RATE_LIMIT_WINDOW: int = 60


def _is_rate_limited(ip: str) -> bool:
    now = time.time()
    with config._rate_limit_lock:
        lst = config._rate_limit.get(ip, [])
        lst = [t for t in lst if now - t < _RATE_LIMIT_WINDOW]
        config._rate_limit[ip] = lst
        return len(lst) >= _RATE_LIMIT_MAX


def _record_failed(ip: str) -> None:
    now = time.time()
    with config._rate_limit_lock:
        lst = config._rate_limit.get(ip, [])
        lst.append(now)
        lst = [t for t in lst if now - t < _RATE_LIMIT_WINDOW]
        config._rate_limit[ip] = lst


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


@app.route('/')
def index() -> str:
    return '''<html><head><title>ScreenCast->browser</title><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<style>html,body{margin:0;height:100%;background:#000;color:#fff;font-family:system-ui}img{width:100%;height:100%;object-fit:contain}#status{position:fixed;top:8px;left:8px;background:rgba(0,0,0,0.7);padding:6px 10px;border-radius:6px;font-size:12px;max-width:90vw;word-break:break-all}</style>
</head>
<body>
<img id="s" alt="Stream">
<div id="status">Connecting...</div>
<script>
const code=new URLSearchParams(location.search).get('code')||'';
const img=document.getElementById('s');
const statusEl=document.getElementById('status');
function vurl(){return '/video'+(code?'?code='+encodeURIComponent(code):'')}
let lastLoad=Date.now();
let retryDelay=700;
let reconnectTimer=null;
let stallTimer=null;
let framePoll=null;
let connecting=false;
let abortCtrl=null;
let lastWidth=0;
function setStatus(t){ statusEl.textContent=t; statusEl.style.display=t?'block':'none'; }
function vurlWithCacheBust(){
  const base=vurl();
  return base + (base.includes('?') ? '&' : '?') + 't=' + Date.now() + '&r=' + Math.random().toString(36).slice(2,7);
}
function connect(){
  if(connecting) return;
  connecting=true;
  // reset state - critical for restart case
  retryDelay=700;
  lastLoad=Date.now();
  clearTimeout(reconnectTimer); reconnectTimer=null;
  if(abortCtrl) try{abortCtrl.abort();}catch(e){}
  abortCtrl=null;
  try{ img.src=''; img.removeAttribute('src'); }catch(e){}
  // force abort previous request in some browsers
  try{ if(img.decode) {} }catch(e){}
  const u=vurlWithCacheBust();
  console.log('[connect]',new Date().toLocaleTimeString(),u);
  setStatus('Connecting...');
  setTimeout(()=>{ img.src=u; connecting=false; }, 80);
}
img.onload=()=>{
  lastLoad=Date.now();
  retryDelay=700;
  lastWidth=img.naturalWidth;
  setStatus('');
  console.log('[onload]',new Date().toLocaleTimeString(), 'w='+img.naturalWidth);
};
img.onerror=(e)=>{
  console.log('[onerror]',new Date().toLocaleTimeString(),e);
  if(connecting) return;
  if(abortCtrl) try{abortCtrl.abort();}catch(e){}
  abortCtrl=new AbortController();
  fetch(vurl(),{method:'HEAD', cache:'no-store', signal:abortCtrl.signal}).then(r=>{
    if(r.status===403) setStatus('403 Forbidden - wrong access code');
    else if(r.status===429) setStatus('429 Too many attempts - wait');
    else setStatus('Error - retrying in '+Math.round(retryDelay)+'ms');
  }).catch(err=>{
    if(err && err.name==='AbortError') return;
    setStatus('Network error - retrying');
  });
  const d=retryDelay;
  retryDelay=Math.min(retryDelay*1.6, 8000);
  clearTimeout(reconnectTimer);
  reconnectTimer=setTimeout(connect, d);
};
console.log('[start]',new Date().toLocaleTimeString(),location.href);
connect();
// Poll naturalWidth to detect MJPEG frames - onload fires only once for multipart
framePoll=setInterval(()=>{
  if(img.naturalWidth && img.naturalWidth!==lastWidth){
    lastWidth=img.naturalWidth;
    lastLoad=Date.now();
    retryDelay=700;
    setStatus('');
  }
}, 500);
stallTimer=setInterval(()=>{
  if(document.hidden) return;
  if(connecting) return;
  const idle=Date.now()-lastLoad;
  const noFrame = !img.naturalWidth;
  if(idle>4000 || (noFrame && idle>2500)){
    console.log('[stall] idle='+idle+'ms, w='+img.naturalWidth+' -> reconnect');
    setStatus('Stalled - reconnecting...');
    connect();
  }
},1500);
document.addEventListener('visibilitychange',()=>{
  if(!document.hidden){
    console.log('[visible] resume');
    // only reconnect if actually stalled, not every visibility change
    const idle=Date.now()-lastLoad;
    if(idle>2000 || !img.naturalWidth){
      lastLoad=Date.now();
      connect();
    }
  }
});
window.addEventListener('beforeunload',()=>{
  clearInterval(stallTimer);
  clearInterval(framePoll);
  clearTimeout(reconnectTimer);
  if(abortCtrl) try{abortCtrl.abort();}catch(e){}
  try{ img.src=''; }catch(e){}
});
</script>
</body></html>'''


@app.route('/ping')
def ping() -> Any:
    if not is_authorized(request):
        abort(403)
    return 'ok', 200


@app.route('/video')
def video() -> Any:
    if not is_authorized(request):
        abort(403, description="Invalid access code")
    resp = Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    # Critical for restart: force close so browser doesn't reuse stale keep-alive socket
    resp.headers['Connection'] = 'close'
    resp.headers['X-Accel-Buffering'] = 'no'
    return resp


def _check_port_available(port: int) -> None:
    """Pre-check if port is free (without SO_REUSEADDR) to detect busy port reliably."""
    if port == 0:
        return
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        except Exception:
            pass
        s.bind(('0.0.0.0', port))
    finally:
        s.close()


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
                with config.server_lock:
                    if config.server is srv:
                        config.server = None
                logger.info("Werkzeug server stopped")
        else:
            with config.server_lock:
                config.server = app
            try:
                logger.info("Flask dev server on 0.0.0.0:%d", port)
                app.run(host='0.0.0.0', port=port, threaded=True, use_reloader=False)
            finally:
                with config.server_lock:
                    config.server = None
                logger.info("Flask dev server stopped")
    except OSError as e:
        logger.error("Failed to bind port %d: %s", port, e)
        raise
    except Exception as e:
        logger.exception("Server unexpected error on port %d: %s", port, e)
        raise
