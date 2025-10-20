from flask import Flask, request, jsonify, send_from_directory, url_for
from flask_cors import CORS
import os, json, base64, time, sys
from pathlib import Path

# ===== Flask setup =====
app = Flask(__name__)
CORS(app)

# ===== 定数 =====
UPLOAD_DIR = "uploads"
DATA_FILE  = os.path.join(UPLOAD_DIR, "requests.json")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ===== 共通関数 =====
def _now(): return int(time.time())
def _load_all():
    if not os.path.exists(DATA_FILE): return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try: return json.load(f)
        except: return []
def _save_all(arr): open(DATA_FILE,"w",encoding="utf-8").write(json.dumps(arr,ensure_ascii=False,indent=2))
def _add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"]  = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    return resp
def _public_base():
    return os.getenv("RENDER_EXTERNAL_URL", "https://anone-project.onrender.com")

# ===== ルート群 =====
@app.route("/health")
def health(): return jsonify(ok=True)

@app.route("/__ping")
def ping(): return jsonify(ok=True, ts=_now())

@app.route("/__routes")
def routes():
    out=[]
    for r in app.url_map.iter_rules():
        out.append({ "route": str(r), "methods": list(r.methods) })
    return jsonify(routes=out)

@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# ===== POST /requests =====
def _smart_payload():
    ctype = (request.content_type or "").lower()
    if "application/json" in ctype:
        data = request.get_json(silent=True) or {}
        files = {}
    elif "multipart/form-data" in ctype:
        data = {k: request.form.get(k) for k in request.form}
        files = request.files
    else:
        data = request.get_json(silent=True) or {}
        files = {}
    return data, files

@app.route("/requests", methods=["POST"])
@app.route("/requests/", methods=["POST"])
def requests_create():
    try:
        data, files = _smart_payload()
        payload = data if isinstance(data, dict) else {}
        rec = payload.get("record", {}) or {k: v for k,v in payload.items() if k not in ("image_b64","image_ext","token")}
        img_b64 = payload.get("image_b64", "") or ""
        img_url = None

        if "image" in files and files["image"]:
            f = files["image"]
            ext = (Path(f.filename).suffix.lower().lstrip(".") or "png")
            if ext not in ("png","jpg","jpeg","webp"): ext="png"
            fname=f"{_now()}.{ext}"
            save_path=os.path.join(UPLOAD_DIR,fname)
            f.save(save_path)
            img_url=_public_base()+url_for("serve_upload",filename=fname)

        elif img_b64:
            ext=(payload.get("image_ext","png") or "png").lower()
            if ext not in ("png","jpg","jpeg","webp"): ext="png"
            if img_b64.startswith("data:"):
                i=img_b64.find("base64,")
                if i!=-1: img_b64=img_b64[i+7:]
            img_bytes=base64.b64decode(img_b64,validate=False)
            fname=f"{_now()}.{ext}"
            save_path=os.path.join(UPLOAD_DIR,fname)
            open(save_path,"wb").write(img_bytes)
            img_url=_public_base()+url_for("serve_upload",filename=fname)

        arr=_load_all()
        rid=rec.get("id") or str(_now())
        rec["id"]=rid
        rec.setdefault("created_at",time.strftime("%Y-%m-%dT%H:%M:%S"))
        rec["created_at_ts"]=_now()
        if img_url: rec["image_url"]=img_url
        arr.append(rec)
        _save_all(arr)

        resp=jsonify(ok=True,id=rid,saved=img_url,item=rec)
        resp.status_code=201
        return _add_cors(resp)
    except Exception as e:
        print("[ERROR] POST /requests:",repr(e),file=sys.stderr)
        return _add_cors(jsonify(ok=False,error="server_error",detail=str(e))),500

# ===== GET /requests =====
@app.route("/requests", methods=["GET"])
@app.route("/requests/", methods=["GET"])
def requests_list():
    arr=_load_all()
    return _add_cors(jsonify(ok=True,items=arr))

# ===== main =====
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
