"""
server.py - Flask server and streaming
"""
from flask import Flask, Response, request, abort
import config
from capture import generate

app = Flask(__name__)


def is_authorized(req):
    """Check access code"""
    code_required = config.config.get("access_code", "")
    if not code_required:
        return True
    return req.args.get("code", "") == code_required


@app.route('/')
def index():
    return '''<html><head><title>ScreenCast->browser</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#000;display:flex;justify-content:center;align-items:center;height:100vh;overflow:hidden;font-family:sans-serif}
#stream{width:100%;height:100%;object-fit:contain}
#overlay{position:fixed;inset:0;background:rgba(0,0,0,0.85);display:none;flex-direction:column;justify-content:center;align-items:center;gap:16px;color:#fff;z-index:10}
#overlay.show{display:flex}
.spinner{width:44px;height:44px;border:4px solid #333;border-top-color:#0f0;border-radius:50%;animation:spin 0.8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
#status{font-size:15px;opacity:0.9}
#retry{font-size:13px;color:#aaa}
.btn{margin-top:8px;padding:8px 18px;background:#0a84ff;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:14px}
.btn:hover{background:#006ed1}
</style>
</head>
<body>
<img id="stream" alt="">
<div id="overlay">
  <div class="spinner" id="spinner"></div>
  <div id="status">Connecting...</div>
  <div id="retry"></div>
  <button class="btn" onclick="connect(true)">Reconnect now</button>
</div>
<script>
const params = new URLSearchParams(window.location.search);
const code = params.get('code') || '';
const img = document.getElementById('stream');
const overlay = document.getElementById('overlay');
const statusEl = document.getElementById('status');
const retryEl = document.getElementById('retry');
let retryCount = 0;
let retryTimer = null;
let stallTimer = null;
let lastLoad = Date.now();
function videoUrl(){
  return '/video' + (code ? '?code=' + encodeURIComponent(code) : '') + '&t=' + Date.now();
}
function showOverlay(msg, sub){
  overlay.classList.add('show');
  statusEl.textContent = msg;
  retryEl.textContent = sub || '';
}
function hideOverlay(){ overlay.classList.remove('show'); }
function connect(manual){
  if(retryTimer){ clearTimeout(retryTimer); retryTimer=null; }
  if(stallTimer){ clearTimeout(stallTimer); }
  if(manual) retryCount = 0;
  showOverlay(retryCount===0 ? 'Connecting...' : 'Reconnecting...', retryCount>0 ? 'Attempt '+(retryCount+1) : '');
  img.src = videoUrl();
  lastLoad = Date.now();
  stallTimer = setTimeout(()=> {
    if(Date.now() - lastLoad > 3500){ handleError('Connection stalled'); }
  }, 4000);
}
function scheduleRetry(reason){
  retryCount++;
  const delay = Math.min(1000 * Math.pow(1.5, retryCount-1), 10000);
  const sec = (delay/1000).toFixed(1);
  showOverlay(reason || 'Connection lost', 'Retrying in '+sec+'s (attempt '+retryCount+')');
  retryTimer = setTimeout(()=> connect(false), delay);
}
function handleError(reason){
  if(stallTimer) clearTimeout(stallTimer);
  fetch(videoUrl(), {method:'HEAD', cache:'no-store'}).then(r=>{
    if(r.status===403){ showOverlay('Access denied - invalid code', 'Check ?code= in URL'); return; }
    scheduleRetry(reason);
  }).catch(()=> scheduleRetry(reason));
}
img.onload = function(){
  hideOverlay(); retryCount = 0; lastLoad = Date.now();
  if(stallTimer) clearTimeout(stallTimer);
  stallTimer = setTimeout(()=> handleError('Stream timeout'), 5000);
};
img.onerror = function(){ handleError('Connection error'); };
window.addEventListener('online', ()=> connect(true));
window.addEventListener('beforeunload', ()=> { if(retryTimer) clearTimeout(retryTimer); });
connect(false);
</script>
</body></html>'''


@app.route('/video')
def video():
    if not is_authorized(request):
        abort(403, description="Invalid access code")
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')


def run_server(port):
    if config.HAS_WERKZEUG:
        config.server = config.make_server('0.0.0.0', port, app, threaded=True)
        config.server.serve_forever()
    else:
        app.run(host='0.0.0.0', port=port, threaded=True, use_reloader=False)
