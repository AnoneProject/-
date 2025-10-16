from flask import Flask, request, jsonify
import os, base64, datetime

app = Flask(__name__)

AUTH_TOKEN = os.getenv("AUTH_TOKEN", "change-me-super-secret")
UPLOAD_DIR = "/tmp/data/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.route("/healthz", methods=["GET"])
def healthz():
	app.logger.info("✅ healthz check OK")
	return jsonify({"ok": True, "msg": "healthy"})

@app.route("/requests", methods=["POST"])
def handle_request():
	auth_header = request.headers.get("Authorization", "")
	if auth_header != f"Bearer {AUTH_TOKEN}":
		app.logger.warning("❌ Unauthorized: invalid token")
		return jsonify({"ok": False, "error": "unauthorized"}), 401

	data = request.get_json(force=True)
	if not data or "record" not in data:
		return jsonify({"ok": False, "error": "bad_request"}), 400

	record = data["record"]
	img_b64 = data.get("image_b64", "")
	filename = f"{record.get('id','noid')}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.png"
	save_path = os.path.join(UPLOAD_DIR, filename)

	if img_b64:
		with open(save_path, "wb") as f:
			f.write(base64.b64decode(img_b64))

	app.logger.info(f"✅ saved: {save_path}")
	return jsonify({"ok": True, "id": record.get("id"), "saved": f"uploads/{filename}"})

if __name__ == "__main__":
	port = int(os.environ.get("PORT", 10000))  # ← Renderが使うポート
	app.run(host="0.0.0.0", port=port)

