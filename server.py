"""
server.py - Flask server and streaming (Phase 4: fixed restart stutter)
"""
import logging
import time
import secrets
import socket
from typing import Any

from flask import Flask, Response, request, abort, jsonify
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
function surl(){return '/status'+(code?'?code='+encodeURIComponent(code):'')}
let currentGen=-1;
let lastFrameId=-1;
let lastAdvance=Date.now();
let retryDelay=700;
let reconnectTimer=null;
let statusTimer=null;
let connecting=false;
let abortCtrl=null;
function setStatus(t){ statusEl.textContent=t; statusEl.style.display=t?'block':'none'; }
function vurlWithCacheBust(){
  const base=vurl();
  return base + (base.includes('?') ? '&' : '?') + 't=' + Date.now() + '&r=' + Math.random().toString(36).slice(2,7);
}
function scheduleReconnect(d){
  clearTimeout(reconnectTimer);
  reconnectTimer=setTimeout(connect, d);
}
function connect(){
  if(connecting) return;
  connecting=true;
  clearTimeout(reconnectTimer); reconnectTimer=null;
  if(abortCtrl) try{abortCtrl.abort();}catch(e){}
  abortCtrl=null;
  // Drop stale keep-alive socket: blank the element before assigning new URL
  try{ img.src='about:blank'; img.removeAttribute('src'); }catch(e){}
  const u=vurlWithCacheBust();
  console.log('[connect]',new Date().toLocaleTimeString(),u,'gen='+currentGen);
  setStatus('Connecting...');
  setTimeout(()=>{ img.src=u; connecting=false; }, 80);
}
img.onload=()=>{
  console.log('[onload]',new Date().toLocaleTimeString(), 'w='+img.naturalWidth);
  setStatus('');
};
img.onerror=(e)=>{
  console.log('[onerror]',new Date().toLocaleTimeString(),e);
  if(connecting) return;
  const d=retryDelay;
  retryDelay=Math.min(retryDelay*1.6, 8000);
  setStatus('Error - retrying in '+Math.round(d)+'ms');
  scheduleReconnect(d);
};
async function checkStatus(){
  if(document.hidden) return;
  try{
    const r=await fetch(surl(),{cache:'no-store'});
    if(r.status===403){ setStatus('403 Forbidden - wrong access code'); return; }
    if(r.status===429){ setStatus('429 Too many attempts - wait'); return; }
    if(!r.ok) throw new Error('http '+r.status);
    const data=await r.json();
    const now=Date.now();
    if(currentGen===-1){
      currentGen=data.generation; lastFrameId=data.frame_id; lastAdvance=now;
      retryDelay=700; setStatus('');
      return;
    }
    if(data.generation!==currentGen){
      console.log('[gen-change]',currentGen,'->',data.generation);
      currentGen=data.generation; lastFrameId=data.frame_id; lastAdvance=now;
      retryDelay=700;
      connect();
      return;
    }
    if(data.frame_id!==lastFrameId){
      lastFrameId=data.frame_id; lastAdvance=now;
      retryDelay=700; setStatus('');
    }else{
      const idle=now-lastAdvance;
      if(idle>2500 && !connecting){
        console.log('[stall] idle='+idle+'ms frame='+data.frame_id+' -> reconnect');
        setStatus('Stalled - reconnecting...');
        lastAdvance=now;
        connect();
      }
    }
  }catch(err){
    // Server down: backoff probe, do not spam <img> connects
    console.log('[status-fail]',new Date().toLocaleTimeString(),String(err&&err.message||err));
    setStatus('Server down - retrying in '+Math.round(retryDelay)+'ms');
    const d=retryDelay;
    retryDelay=Math.min(retryDelay*1.6, 8000);
    scheduleReconnect(d);
  }
}
console.log('[start]',new Date().toLocaleTimeString(),location.href);
connect();
statusTimer=setInterval(checkStatus,1000);
document.addEventListener('visibilitychange',()=>{
  if(!document.hidden){
    console.log('[visible] probe status');
    checkStatus();
  }
});
window.addEventListener('beforeunload',()=>{
  clearInterval(statusTimer);
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
    with config.lock:
        gen = int(config.stream_generation)
    resp = Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    # Critical for restart: force close so browser doesn't reuse stale keep-alive socket
    resp.headers['Connection'] = 'close'
    resp.headers['X-Accel-Buffering'] = 'no'
    resp.headers['X-Stream-Generation'] = str(gen)
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
