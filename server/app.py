# 追加: どの形式でも安全に取り出すヘルパ
def _smart_payload():
    ctype = (request.content_type or "").lower()
    if "application/json" in ctype:
        data = request.get_json(silent=True) or {}
        files = {}
    elif "multipart/form-data" in ctype:
        data = {}
        # テキスト項目
        for k in request.form:
            data[k] = request.form.get(k)
        # ファイル
        files = request.files
    else:
        # フロントが素の fetch で body=FormData のときはここに来ることがある
        data = request.get_json(silent=True) or {}
        files = {}
    return data, files

@app.route("/requests", methods=["POST"])
@app.route("/requests/", methods=["POST"])
def requests_create():
    try:
        data, files = _smart_payload()

        # 既存互換: record / image_b64 / image_ext も拾う
        payload = data if isinstance(data, dict) else {}
        rec = payload.get("record", {}) or {
            k: v for k, v in payload.items() if k not in ("image_b64", "image_ext", "token")
        }

        img_b64 = payload.get("image_b64", "") or ""
        img_url = None

        # (A) multipart でファイルが来た場合: name='image' を想定
        if "image" in files and files["image"]:
            f = files["image"]
            ext = (Path(f.filename).suffix.lower().lstrip(".") or "png")
            if ext not in ("png","jpg","jpeg","webp"): ext = "png"
            fname = f"{_now()}.{ext}"
            save_path = os.path.join(UPLOAD_DIR, fname)
            f.save(save_path)
            img_url = _public_base() + url_for("serve_upload", filename=fname)

        # (B) JSON(base64) で来た場合
        elif img_b64:
            ext = (payload.get("image_ext", "png") or "png").lower()
            if ext not in ("png","jpg","jpeg","webp"): ext = "png"
            if img_b64.startswith("data:"):
                i = img_b64.find("base64,")
                if i != -1:
                    img_b64 = img_b64[i+7:]
            img_bytes = base64.b64decode(img_b64, validate=False)
            fname = f"{_now()}.{ext}"
            save_path = os.path.join(UPLOAD_DIR, fname)
            with open(save_path, "wb") as w:
                w.write(img_bytes)
            img_url = _public_base() + url_for("serve_upload", filename=fname)

        # 保存
        arr = _load_all()
        rec = dict(rec)
        rid = rec.get("id") or f"{_now()}"
        rec["id"] = str(rid)
        rec.setdefault("created_at", time.strftime("%Y-%m-%dT%H:%M:%S"))
        rec["created_at_ts"] = _now()
        if img_url:
            rec["image_url"] = img_url

        arr.append(rec)
        _save_all(arr)

        resp = jsonify(ok=True, id=rec["id"], saved=img_url, item=rec)
        resp.status_code = 201
        return _add_cors(resp)

    except Exception as e:
        # 例外は 500 を JSON で確実に返す（Render の 502 を避ける）
        print("[ERROR] POST /requests:", repr(e), file=sys.stderr)
        return _add_cors(jsonify(ok=False, error="server_error", detail=str(e))), 500
