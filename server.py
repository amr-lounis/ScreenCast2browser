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
<style>html,body{margin:0;height:100%;background:#000}img{width:100%;height:100%;object-fit:contain}</style>
</head>
<body>
<img id="s">
<script>
const code=new URLSearchParams(location.search).get('code')||'';
const img=document.getElementById('s');
function vurl(){return '/video'+(code?'?code='+encodeURIComponent(code):'')}
function purl(){return '/ping'+(code?'?code='+encodeURIComponent(code):'')}
let wasDown=false,failCount=0,lastLoad=Date.now();
function connect(){
  const u=vurl()+(vurl().includes('?')?'&':'?')+'t='+Date.now();
  console.log('[connect]',new Date().toLocaleTimeString(),u);
  lastLoad=Date.now();
  img.src=u;
}
img.onload=()=>{lastLoad=Date.now();console.log('[onload]',new Date().toLocaleTimeString());};
img.onerror=(e)=>{console.log('[onerror]',new Date().toLocaleTimeString(),e);wasDown=true;console.log('[wasDown=true] onerror');setTimeout(connect,700)};
console.log('[start]',new Date().toLocaleTimeString(),location.href);
connect();
function doPing(){
  fetch(purl(),{cache:'no-store'}).then(r=>{
    console.log('[ping]',new Date().toLocaleTimeString(),r.status,'wasDown='+wasDown,'fail='+failCount);
    if(r.status===403) return;
    if(r.ok){
      failCount=0;
      if(wasDown){console.log('[reconnect] ping ok after down');wasDown=false;connect();}
    } else {
      failCount++;
      console.log('[ping fail]',failCount);
      if(!wasDown){wasDown=true;console.log('[wasDown=true] fail');}
    }
  }).catch(err=>{
    failCount++;
    console.log('[ping error]',new Date().toLocaleTimeString(),err.message,'fail='+failCount,'wasDown='+wasDown);
    if(!wasDown){wasDown=true;console.log('[wasDown=true] error');}
  }).finally(()=>setTimeout(doPing,700));
}
doPing();
// stall detection for very short outages missed by ping
setInterval(()=>{
  const idle=Date.now()-lastLoad;
  if(idle>2500 && !wasDown){
    console.log('[stall] no onload for '+idle+'ms');
    wasDown=true;
  }
},1000);
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
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')


def run_server(port):
    if config.HAS_WERKZEUG:
        config.server = config.make_server('0.0.0.0', port, app, threaded=True)
        config.server.serve_forever()
    else:
        app.run(host='0.0.0.0', port=port, threaded=True, use_reloader=False)
