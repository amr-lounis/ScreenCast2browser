"""
server.py - Flask server and streaming
"""
import time
import secrets
import socket
from flask import Flask, Response, request, abort
import config
from capture import generate

app = Flask(__name__)

# Rate-limit: 10 failed attempts per 60s per IP
_RATE_LIMIT_MAX = 10
_RATE_LIMIT_WINDOW = 60


def _is_rate_limited(ip: str) -> bool:
    now = time.time()
    with config._rate_limit_lock:
        lst = config._rate_limit.get(ip, [])
        # prune old
        lst = [t for t in lst if now - t < _RATE_LIMIT_WINDOW]
        config._rate_limit[ip] = lst
        return len(lst) >= _RATE_LIMIT_MAX


def _record_failed(ip: str):
    now = time.time()
    with config._rate_limit_lock:
        lst = config._rate_limit.get(ip, [])
        lst.append(now)
        # prune
        lst = [t for t in lst if now - t < _RATE_LIMIT_WINDOW]
        config._rate_limit[ip] = lst


def is_authorized(req):
    """Check access code - timing-safe, supports header and query"""
    code_required = config.config.get("access_code", "")
    if not code_required:
        return True
    # Support both query ?code= and header X-Access-Code (avoids URL logging)
    provided = req.args.get("code", "")
    if not provided:
        provided = req.headers.get("X-Access-Code", "")
    # Use constant-time comparison
    try:
        ok = secrets.compare_digest(provided, code_required)
    except Exception:
        ok = (provided == code_required)
    if not ok:
        # rate-limit check before recording
        ip = req.remote_addr or "unknown"
        if _is_rate_limited(ip):
            abort(429, description="Too many failed attempts")
        _record_failed(ip)
    return ok


@app.route('/')
def index():
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
let connecting=false;
function setStatus(t){ statusEl.textContent=t; statusEl.style.display=t?'block':'none'; }
function vurlWithCacheBust(){
  const base=vurl();
  return base + (base.includes('?') ? '&' : '?') + 't=' + Date.now();
}
function connect(){
  if(connecting) return;
  connecting=true;
  // Abort previous stream to avoid connection leak
  try{ img.src=''; img.removeAttribute('src'); }catch(e){}
  const u=vurlWithCacheBust();
  console.log('[connect]',new Date().toLocaleTimeString(),u);
  setStatus('Connecting...');
  lastLoad=Date.now();
  // Small delay to let browser abort previous request before new
  setTimeout(()=>{ img.src=u; connecting=false; }, 50);
}
img.onload=()=>{
  lastLoad=Date.now();
  retryDelay=700;
  setStatus('');
  console.log('[onload]',new Date().toLocaleTimeString());
};
img.onerror=(e)=>{
  console.log('[onerror]',new Date().toLocaleTimeString(),e);
  // Detect 403 via fetch probe (img error hides status)
  fetch(vurl(),{method:'HEAD'}).then(r=>{
    if(r.status===403) setStatus('403 Forbidden - wrong access code');
    else if(r.status===429) setStatus('429 Too many attempts - wait');
    else setStatus('Error - retrying in '+Math.round(retryDelay)+'ms');
  }).catch(()=> setStatus('Network error - retrying'));
  const d=retryDelay;
  retryDelay=Math.min(retryDelay*1.6, 8000);
  clearTimeout(reconnectTimer);
  reconnectTimer=setTimeout(connect, d);
};
console.log('[start]',new Date().toLocaleTimeString(),location.href);
connect();
// Stall detection: if no onload for fps-dependent interval, reconnect
// Use 3 seconds + 1/fps slack; assume worst 5fps => 3200ms
stallTimer=setInterval(()=>{
  if(document.hidden) return;
  const idle=Date.now()-lastLoad;
  // Consider naturalWidth check: if img has not loaded any frame, naturalWidth==0
  const noFrame = !img.naturalWidth;
  if(idle>3500 || (noFrame && idle>2000)){
    console.log('[stall] no onload for '+idle+'ms, naturalWidth='+img.naturalWidth+' -> reconnect');
    setStatus('Stalled - reconnecting...');
    connect();
  }
},1500);
document.addEventListener('visibilitychange',()=>{
  if(!document.hidden){
    console.log('[visible] resume');
    lastLoad=Date.now();
    connect();
  }
});
window.addEventListener('beforeunload',()=>{
  clearInterval(stallTimer);
  clearTimeout(reconnectTimer);
  try{ img.src=''; }catch(e){}
});
</script>
</body></html>'''


@app.route('/ping')
def ping():
    if not is_authorized(request):
        abort(403)
    return 'ok', 200


@app.route('/video')
def video():
    if not is_authorized(request):
        abort(403, description="Invalid access code")
    resp = Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


def _check_port_available(port):
    """Pre-check if port is free (without SO_REUSEADDR) to detect busy port reliably."""
    if port == 0:
        return  # OS will assign free port
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        except Exception:
            pass
        s.bind(('0.0.0.0', port))
    finally:
        s.close()


def run_server(port):
    # Try to bind port with proper error propagation (so GUI can detect busy port)
    try:
        _check_port_available(port)
        if config.HAS_WERKZEUG:
            srv = config.make_server('0.0.0.0', port, app, threaded=True)
            with config.server_lock:
                config.server = srv
            try:
                srv.serve_forever()
            finally:
                with config.server_lock:
                    if config.server is srv:
                        config.server = None
        else:
            # Flask dev server - cannot capture make_server errors, but try run
            # Store dummy to allow shutdown detection
            with config.server_lock:
                config.server = app  # marker
            try:
                app.run(host='0.0.0.0', port=port, threaded=True, use_reloader=False)
            finally:
                with config.server_lock:
                    config.server = None
    except OSError as e:
        # Do not clear config.server here - failure before srv assignment should preserve existing running server
        print(f"[server] failed to bind port {port}: {e}")
        raise
    except Exception as e:
        print(f"[server] unexpected error: {e}")
        raise
