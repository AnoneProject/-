# -*- coding: utf-8 -*-
# ====== anone-requests / full app.py ======
print(">>> anone-requests boot:", __file__, flush=True)

from flask import Flask, request, jsonify, redirect, make_response
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
import os, json, base64, time, sys

# ---------- env / paths ----------
load_dotenv()
PORT            = int(os.getenv("PORT", "10000"))
DATA_DIR        = os.getenv("DATA_DIR", "data")
UPLOAD_DIR      = os.getenv("UPLOAD_DIR", "uploads")
MAX_CONTENT_MB  = int(os.getenv("MAX_CONTENT_LENGTH_MB", "10"))
FORCE_HTTPS     = os.getenv("FORCE_HTTPS", "1") == "1"

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---------- app base ----------
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_MB * 1024 * 1024
app.url_map.strict_slashes = False

# ---------- helpers ----------
def _add_cors(resp):
    """Add permissive CORS headers (GET/POST/OPTIONS)."""
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, Authorization, X-Auth-Token, Accept, X-Requested-With"
    )
    resp.headers["Access-Control-Max-Age"] = "86400"
    resp.headers["X-Debug-CORS"] = "hit"
    return resp

def _now_ts() -> int:
    return int(time.time())

def _json():
    return request.get_json(force=True, silent=True) or {}

# ---------- global hooks ----------
@app.before_request
def _force_https():
    # Cloudfront/Render から来るプロキシ環境を考慮し X-Forwarded-Proto を見る
    if FORCE_HTTPS and request.method in ("GET", "POST"):
        if request.headers.get("X-Forwarded-Proto", "http") != "https":
            target = request.url.replace("http://", "https://", 1)
            return redirect(target, code=301)

@app.before_request
def _global_preflight():
    # 共通 OPTIONS 応答
    if request.method == "OPTIONS":
        print("[CORS] global OPTIONS:", request.path, "from", request.headers.get("Origin"), file=sys.stderr)
        resp = make_response("ok")
        resp.status_code = 200
        return _add_cors(resp)

# ---------- basic routes ----------
@app.get("/")
def root():
    return _add_cors(jsonify(ok=True, service="anone-requests")), 200

@app.get("/health")
def health():
    return _add_cors(jsonify(ok=True)), 200

@app.post("/echo")
def echo():
    return _add_cors(jsonify(ok=True, echo=_json())), 200

# ---------- main feature: /requests ----------
@app.route("/requests", methods=["POST"])
@app.route("/requests/", methods=["POST"])
def requests_route():
    payload = _json()

    # record フラット化（image/token 以外を record に）
    rec = payload.get("record", {}) or {k: v for k, v in payload.items() if k not in ("image_b64", "image_ext", "token")}

    # optional image
    img_b64 = payload.get("image_b64", "") or ""
    img_ext = (payload.get("image_ext", "png") or "png").lower()
    if img_ext not in ("png", "jpg", "jpeg", "webp"):
        img_ext = "png"

    saved_img_path = ""
    if img_b64:
        # data URI の場合を剥がす
        if img_b64.startswith("data:"):
            i = img_b64.find("base64,")
            if i != -1:
                img_b64 = img_b64[i + 7 :]
        try:
            img_bytes = base64.b64decode(img_b64, validate=False)
            fname = f"{_now_ts()}.{img_ext}"
            saved_img_path = os.path.join(UPLOAD_DIR, fname)
            with open(saved_img_path, "wb") as f:
                f.write(img_bytes)
        except Exception:
            return _add_cors(jsonify(ok=False, error="invalid_base64")), 400

    # JSON 追記保存
    path = os.path.join(DATA_DIR, "requests.json")
    arr = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as r:
                arr = json.load(r)
                if not isinstance(arr, list):
                    arr = []
        except Exception:
            arr = []

    rec = dict(rec)
    rec.setdefault("id", f"{_now_ts()}")
    rec.setdefault("created_at", time.strftime("%Y-%m-%dT%H:%M:%S"))
    if saved_img_path:
        rec["server_saved_image"] = saved_img_path

    arr.append(rec)
    with open(path, "w", encoding="utf-8") as w:
        json.dump(arr, w, ensure_ascii=False, indent=2)

    return _add_cors(jsonify(ok=True, id=rec["id"], saved=saved_img_path or None)), 201

# ---------- diagnostics (必ず残しておくと便利) ----------
@app.get("/__ping")
def __ping():
    return _add_cors(jsonify(ok=True, ts=_now_ts())), 200

@app.get("/__routes")
def __routes():
    try:
        routes = sorted([f"{r.methods} {r.rule}" for r in app.url_map.iter_rules()])
    except Exception as e:
        routes = [f"error: {e!r}"]
    return _add_cors(jsonify(routes=routes)), 200

# ---------- run local ----------
if __name__ == "__main__":
    # ローカル起動用（Render では gunicorn が使われる）
    app.run(host="0.0.0.0", port=PORT, debug=True)

