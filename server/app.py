# server/app.py
print(">> anone-requests loaded from", __file__)
APP_VERSION = "v2025-10-20-final"
print(">>> Deploy version:", APP_VERSION)

from flask import Flask, request, jsonify, redirect, make_response, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
import os, json, base64, time, sys
from pathlib import Path

# -----------------------------
# Config
# -----------------------------
load_dotenv()
PORT            = int(os.getenv("PORT", "10000"))
DATA_DIR        = os.getenv("DATA_DIR", "data")
UPLOAD_DIR      = os.getenv("UPLOAD_DIR", "uploads")
MAX_CONTENT_MB  = int(os.getenv("MAX_CONTENT_LENGTH_MB", "10"))
FORCE_HTTPS     = os.getenv("FORCE_HTTPS", "1") == "1"

Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

# -----------------------------
# Flask
# -----------------------------
app = Flask(__name__)
# Render/Cloudflare の背後に居るので proxy 情報を正しく解釈
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
# 最大アップロードサイズ
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_MB * 1024 * 1024
# 末尾スラッシュの違いで 404 にしない
app.url_map.strict_slashes = False

# -----------------------------
# Helpers
# -----------------------------
def _add_cors(resp):
    """全レスポンスにCORSを付与"""
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, Authorization, X-Auth-Token, Accept, X-Requested-With"
    )
    resp.headers["Access-Control-Max-Age"] = "86400"
    resp.headers["X-Debug-CORS"] = "hit"
    return resp

def _now() -> int:
    return int(time.time())

def _json() -> dict:
    return request.get_json(force=True, silent=True) or {}

def _routes_snapshot() -> list:
    out = []
    for r in app.url_map.iter_rules():
        out.append([list(r.methods), str(r.rule)])
    return out

# -----------------------------
# Middlewares
# -----------------------------
@app.before_request
def _force_https():
    # GET/POST のとき http なら https に 301
    if request.method in ("GET", "POST") and FORCE_HTTPS:
        if request.headers.get("X-Forwarded-Proto", "http") != "https":
            https_url = request.url.replace("http://", "https://", 1)
            return redirect(https_url, code=301)

@app.before_request
def _global_preflight():
    # ブラウザのプリフライト OPTIONS をここで即返す
    if request.method == "OPTIONS":
        print("[CORS] global OPTIONS:", request.path, "from", request.headers.get("Origin"), file=sys.stderr)
        resp = make_response("ok")
        resp.status_code = 200
        return _add_cors(resp)

@app.after_request
def _after(resp):
    return _add_cors(resp)

# -----------------------------
# Routes
# -----------------------------
@app.get("/")
def root():
    return jsonify(ok=True, service="anone-requests", version=APP_VERSION), 200

@app.get("/health")
def health():
    return jsonify(ok=True), 200

@app.get("/__ping")
def ping():
    return jsonify(ok=True, ts=_now()), 200

@app.get("/__routes")
def routes_view():
    return jsonify(routes=_routes_snapshot()), 200

@app.post("/echo")
def echo():
    return jsonify(ok=True, echo=_json()), 200

@app.route("/requests", methods=["POST"])
@app.route("/requests/", methods=["POST"])
def requests_route():
    """
    受信JSON:
      {
        "record": {...},            # 任意
        "image_b64": "data:..",     # 任意 base64(先頭に data: が付いてても可)
        "image_ext": "png|jpg|jpeg|webp" # 任意（既定png）
      }
    保存先:
      data/requests.json （配列append）
      uploads/{epoch}.{ext}
    """
    payload = _json()

    # record は "record" が無ければ入力全体から image/token系を除外して作る
    rec = payload.get("record", {}) or {
        k: v for k, v in payload.items() if k not in ("image_b64", "image_ext", "token")
    }

    # 画像
    img_b64 = (payload.get("image_b64") or "").strip()
    img_ext = (payload.get("image_ext", "png") or "png").lower()
    if img_ext not in ("png", "jpg", "jpeg", "webp"):
        img_ext = "png"

    img_path = ""
    if img_b64:
        # dataURL の場合はカンマ以降を抜き出し
        if img_b64.startswith("data:"):
            i = img_b64.find("base64,")
            if i != -1:
                img_b64 = img_b64[i + 7 :]
        try:
            img_bytes = base64.b64decode(img_b64, validate=False)
            fname = f"{_now()}.{img_ext}"
            img_path = str(Path(UPLOAD_DIR) / fname)
            with open(img_path, "wb") as f:
                f.write(img_bytes)
        except Exception as e:
            return jsonify(ok=False, error="invalid_base64", detail=str(e)), 400

    # 既存の requests.json を配列として読み込む
    data_file = Path(DATA_DIR) / "requests.json"
    arr = []
    if data_file.exists():
        try:
            arr = json.loads(data_file.read_text(encoding="utf-8"))
            if not isinstance(arr, list):
                arr = []
        except Exception:
            arr = []

    # レコード整形
    rec = dict(rec)
    rec.setdefault("id", f"{_now()}")
    rec.setdefault("created_at", time.strftime("%Y-%m-%dT%H:%M:%S"))
    if img_path:
        rec["server_saved_image"] = img_path

    # 保存
    arr.append(rec)
    data_file.write_text(json.dumps(arr, ensure_ascii=False, indent=2), encoding="utf-8")

    return jsonify(ok=True, id=rec["id"], saved=(img_path or None)), 201

# 任意: 保存した画像をブラウザから確認したい場合
@app.get("/uploads/<path:filename>")
def uploads_file(filename):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
