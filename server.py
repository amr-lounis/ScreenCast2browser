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
let wasDown=false;
function connect(){
  wasDown=false;
  try{img.src='';}catch(e){}
  try{img.removeAttribute('src');}catch(e){}
  void img.offsetWidth;
  setTimeout(()=>{img.src=vurl()+(vurl().includes('?')?'&':'?')+'t='+Date.now()},80);
}
img.onerror=()=>{wasDown=true;setTimeout(connect,600)};
connect();
setInterval(()=>{
  fetch(purl(),{cache:'no-store'}).then(r=>{
    if(r.status===403) return;
    if(r.ok){
      if(wasDown) connect();
    } else {
      wasDown=true;
    }
  }).catch(()=>{wasDown=true});
},1200);
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
