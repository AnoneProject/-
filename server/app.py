# app.py
import os
import json
import time
import base64
import uuid
from typing import List

from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix


# ========= 環境変数 =========
PORT = int(os.getenv("PORT", "10000"))  # Renderは$PORTを渡してくれる
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "")  # 空なら認証なし
ALLOW_ORIGINS_ENV = os.getenv("ALLOW_ORIGINS", "*")
DATA_DIR = os.getenv("DATA_DIR", "/tmp/data")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(DATA_DIR, "uploads"))
MAX_CONTENT_LENGTH_MB = int(os.getenv("MAX_CONTENT_LENGTH_MB", "10"))
FORCE_HTTPS = os.getenv("FORCE_HTTPS", "0") == "1"

# ========= Flask 準備 =========
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.config["JSON_AS_ASCII"] = False
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH_MB * 1024 * 1024

# CORS 許可
if ALLOW_ORIGINS_ENV.strip() == "*" or ALLOW_ORIGINS_ENV.strip() == "":
    CORS(app, resources={r"/*": {"origins": "*"}})
else:
    origins: List[str] = [o.strip() for o in ALLOW_ORIGINS_ENV.split(",") if o.strip()]
    CORS(app, resources={r"/*": {"origins": origins}})

# ディレクトリ作成
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

REQUESTS_JSON_PATH = os.path.join(DATA_DIR, "requests.json")


# ========= ユーティリティ =========
def auth_ok(req) -> bool:
    if not AUTH_TOKEN:
        return True
    return req.headers.get("Authorization") == f"Bearer {AUTH_TOKEN}"


def save_image_from_b64(image_b64: str) -> str:
    """
    Base64画像を保存して、相対パスを返す（例: uploads/1699999999_abcd.png）
    空文字なら空文字を返す。
    """
    if not image_b64:
        return ""

    try:
        img_bytes = base64.b64decode(image_b64.encode("utf-8"), validate=True)
    except Exception:
        # Base64が壊れている
        raise ValueError("invalid_base64")

    stamp = int(time.time())
    name = f"{stamp}_{uuid.uuid4().hex[:6]}.png"
    abs_path = os.path.join(UPLOAD_DIR, name)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "wb") as f:
        f.write(img_bytes)

    # クライアントへはサーバー内の公開相対パスを返す
    return f"uploads/{name}"


def append_request_record(record: dict) -> None:
    """DATA_DIR/requests.json に配列として追記保存（UTF-8, pretty）。"""
    arr = []
    if os.path.exists(REQUESTS_JSON_PATH):
        try:
            with open(REQUESTS_JSON_PATH, "r", encoding="utf-8") as r:
                arr = json.load(r)
        except Exception:
            arr = []
    arr.append(record)
    with open(REQUESTS_JSON_PATH, "w", encoding="utf-8") as w:
        json.dump(arr, w, ensure_ascii=False, indent=2)


# ========= ルート =========
@app.route("/")
def root():
    # 生存確認用（任意でOK）
    return "ok", 200


@app.route("/healthz")
def healthz():
    return "OK", 200


@app.post("/requests")
def receive():
    # 認証
    if not auth_ok(request):
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    # JSON 取得
    try:
        payload = request.get_json(force=True, silent=False)
    except Exception as e:
        return jsonify({"ok": False, "error": f"invalid_json: {e}"}), 400

    try:
        rec = payload.get("record", {}) if isinstance(payload, dict) else {}
        image_b64 = payload.get("image_b64", "") if isinstance(payload, dict) else ""

        # 画像保存（あってもなくてもOK）
        saved_path = save_image_from_b64(image_b64)
        if saved_path:
            rec["server_saved_image"] = saved_path

        # リクエスト保存
        append_request_record(rec)

        return jsonify({
            "ok": True,
            "id": rec.get("id"),
            "saved": saved_path
        }), 201

    except ValueError as ve:
        # 例: invalid_base64
        return jsonify({"ok": False, "error": str(ve)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# （将来の拡張）multipart/form-data 版
@app.post("/requests-mp")
def receive_multipart():
    if not auth_ok(request):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    try:
        record_json = request.form.get("record_json", "{}")
        rec = json.loads(record_json)
        file = request.files.get("image")

        saved_path = ""
        if file:
            stamp = int(time.time())
            name = f"{stamp}_{uuid.uuid4().hex[:6]}.png"
            abs_path = os.path.join(UPLOAD_DIR, name)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            file.save(abs_path)
            saved_path = f"uploads/{name}"
            rec["server_saved_image"] = saved_path

        append_request_record(rec)
        return jsonify({"ok": True, "saved": saved_path}), 201

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


# ========= ローカル実行用 =========
if __name__ == "__main__":
    # Render 本番では gunicorn が使われる。ローカル検証用にだけ起動。
    app.run(host="0.0.0.0", port=PORT, debug=True)
