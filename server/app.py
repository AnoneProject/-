from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
import base64, json, os, time
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix

# --- 環境変数読み込み（ローカル開発用） ---
load_dotenv()

# Render は自動で PORT を渡す
PORT = int(os.getenv("PORT", "5173"))

# 認証トークン（空なら認証なし）
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "")

# CORS 許可オリジン（カンマ区切り）
ALLOW_ORIGINS = [s.strip() for s in os.getenv("ALLOW_ORIGINS", "*").split(",")]

# 永続ディスク or フォルダ（Render の Persistent Disk を /var/data にマウント推奨）
DATA_DIR = os.getenv("DATA_DIR", "data")        # JSON置き場
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads") # 画像置き場
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Flask 本体
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# CORS
CORS(app, resources={r"/*": {"origins": ALLOW_ORIGINS}})
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_CONTENT_LENGTH_MB", "5")) * 1024 * 1024

def auth_ok(req) -> bool:
    if not AUTH_TOKEN:
        return True
    return req.headers.get("Authorization") == f"Bearer {AUTH_TOKEN}"

@app.before_request
def enforce_https():
    # Render は X-Forwarded-Proto を付与（https 常時化／開発中は無効でもOK）
    if os.getenv("FORCE_HTTPS", "1") == "1":
        if request.headers.get("X-Forwarded-Proto", "http") != "https":
            return redirect(request.url.replace("http://", "https://"), code=301)

@app.post("/requests")
def receive():
    if not auth_ok(request):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    try:
        payload = request.get_json(force=True)
        rec = payload.get("record", {})
        img_b64 = payload.get("image_b64", "")

        img_bytes = base64.b64decode(img_b64.encode("utf-8")) if img_b64 else b""
        stamp = int(time.time())

        img_path = os.path.join(UPLOAD_DIR, f"{stamp}.png")
        with open(img_path, "wb") as f:
            f.write(img_bytes)

        # リクエスト保存（配列追記）
        path = os.path.join(DATA_DIR, "requests.json")
        arr = []
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as r:
                    arr = json.load(r)
            except Exception:
                arr = []

        rec["server_saved_image"] = img_path
        arr.append(rec)

        with open(path, "w", encoding="utf-8") as w:
            json.dump(arr, w, ensure_ascii=False, indent=2)

        return jsonify({"ok": True, "id": rec.get("id"), "saved": img_path}), 201

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

# ローカル実行用（Render本番はgunicornで起動）
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
    @app.route("/healthz")
def healthz():
    return "OK", 200
@app.route("/healthz")
def healthz():
    return "OK", 200
