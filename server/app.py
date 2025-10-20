print(">> anone-requests loaded from", __file__)
APP_VERSION = "corsfix-2025-10-20c"
print(">>> Deploy version:", APP_VERSION)

from flask import Flask, request, jsonify, redirect, make_response, send_from_directory, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
import os, json, base64, time, sys
from pathlib import Path

load_dotenv()

PORT           = int(os.getenv("PORT", "10000"))
DATA_DIR       = os.getenv("DATA_DIR", "data")
UPLOAD_DIR     = os.getenv("UPLOAD_DIR", "uploads")
MAX_CONTENT_MB = int(os.getenv("MAX_CONTENT_LENGTH_MB", "10"))
FORCE_HTTPS    = os.getenv("FORCE_HTTPS", "1") == "1"

Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_MB * 1024 * 1024
app.url_map.strict_slashes = False

def _add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Auth-Token, Accept, X-Requested-With"
    resp.headers["Access-Control-Max-Age"] = "86400"
    resp.headers["X-Debug-CORS"] = "hit"
    # 一部フロントがヘッダ読む場合用
    resp.headers["Access-Control-Expose-Headers"] = "Content-Type"
    return resp

@app.before_request
def _force_https():
    if request.method in ("GET","POST") and FORCE_HTTPS:
        if request.headers.get("X-Forwarded-Proto", "http") != "https":
            return redirect(request.url.replace("http://", "https://"), code=301)

@app.before_request
def _global_preflight():
    if request.method == "OPTIONS":
        print("[CORS] global OPTIONS:", request.path, "from", request.headers.get("Origin"), file=sys.stderr)
        resp = make_response("ok")
        resp.status_code = 200
        return _add_cors(resp)

def _now(): return int(time.time())
def _json(): return request.get_json(force=True, silent=True) or {}

def _data_path():
    return os.path.join(DATA_DIR, "requests.json")

def _load_all():
    path = _data_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as r:
                arr = json.load(r)
                return arr if isinstance(arr, list) else []
        except Exception:
            return []
    return []

def _save_all(arr):
    with open(_data_path(), "w", encoding="utf-8") as w:
        json.dump(arr, w, ensure_ascii=False, indent=2)

def _public_base():
    # 例: https://anone-project.onrender.com
    # リバースプロキシ配下で正しいスキーム/ホストが入るよう X-Forwarded-* を信じる
    return request.host_url.rstrip("/")

@app.get("/")
def root():
    return _add_cors(jsonify(ok=True, service="anone-requests", version=APP_VERSION)), 200

@app.get("/__ping")
def ping():
    return _add_cors(jsonify(ok=True, ts=_now())), 200

@app.get("/__routes")
def routes_dump():
    routes = []
    for r in app.url_map.iter_rules():
        routes.append({"rule": str(r), "methods": sorted(list(r.methods - {'HEAD'}))})
    return _add_cors(jsonify(routes=routes)), 200

@app.get("/health")
def health():
    return _add_cors(jsonify(ok=True)), 200

# 画像配信用
@app.get("/uploads/<path:filename>")
def serve_upload(filename):
    return _add_cors(send_from_directory(UPLOAD_DIR, filename, as_attachment=False)), 200

@app.post("/echo")
def echo():
    return _add_cors(jsonify(ok=True, echo=_json())), 200

# ====== requests API ======

# 一覧取得（フロントの右カラムがこれを期待しているはず）
@app.get("/requests")
def list_requests():
    arr = _load_all()
    # 新しい順に返す
    arr_sorted = sorted(arr, key=lambda x: x.get("created_at_ts", 0), reverse=True)
    return _add_cors(jsonify(ok=True, items=arr_sorted)), 200

# 単体取得（必要なら）
@app.get("/requests/<rid>")
def get_request(rid):
    arr = _load_all()
    for it in arr:
        if str(it.get("id")) == str(rid):
            return _add_cors(jsonify(ok=True, item=it)), 200
    return _add_cors(jsonify(ok=False, error="not_found")), 404

# 送信（作成）
@app.route("/requests", methods=["POST"])
@app.route("/requests/", methods=["POST"])
def requests_create():
    payload = _json()

    rec = payload.get("record", {}) or {
        k: v for k, v in payload.items() if k not in ("image_b64", "image_ext", "token")
    }

    img_b64 = payload.get("image_b64", "") or ""
    img_ext = (payload.get("image_ext", "png") or "png").lower()
    if img_ext not in ("png","jpg","jpeg","webp"): img_ext = "png"

    img_path = ""
    img_url = None
    if img_b64:
        if img_b64.startswith("data:"):
            i = img_b64.find("base64,")
            if i != -1:
                img_b64 = img_b64[i+7:]
        try:
            img_bytes = base64.b64decode(img_b64, validate=False)
            fname = f"{_now()}.{img_ext}"
            img_path = os.path.join(UPLOAD_DIR, fname)
            with open(img_path, "wb") as f:
                f.write(img_bytes)
            # 公開URL
            img_url = _public_base() + url_for("serve_upload", filename=fname)
        except Exception:
            return _add_cors(jsonify(ok=False, error="invalid_base64")), 400

    arr = _load_all()

    rec = dict(rec)
    rid = rec.get("id") or f"{_now()}"
    rec["id"] = str(rid)
    rec.setdefault("created_at", time.strftime("%Y-%m-%dT%H:%M:%S"))
    rec["created_at_ts"] = _now()
    if img_path:
        rec["server_saved_image"] = img_path  # サーバ内パス（デバッグ用）
        rec["image_url"] = img_url           # フロント向け公開URL

    arr.append(rec)
    _save_all(arr)

    # フロントが 200 を期待しているケースにも優しい返しにする
    resp = jsonify(ok=True, id=rec["id"], saved=img_url or None, item=rec)
    resp.status_code = 201
    return _add_cors(resp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
