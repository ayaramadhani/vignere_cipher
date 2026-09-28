"""
Aplikasi web Flask: enkripsi/dekripsi file PDF dengan Vigenere cipher.

Alur:
    Browser --(upload PDF + key)--> POST /encrypt atau /decrypt
            <--(PDF hasil proses, otomatis terunduh)--

Endpoint:
    GET  /         halaman form (SEMENTARA, akan diganti templates/index.html)
    POST /encrypt  form-data: file (PDF), key (teks)  -> PDF terenkripsi
    POST /decrypt  form-data: file (PDF), key (teks)  -> PDF asli

Kesalahan dikembalikan sebagai JSON {"error": "..."} supaya mudah
ditampilkan oleh frontend.

Jalankan dari folder root proyek:
    python app.py
lalu buka http://127.0.0.1:5000
"""

from __future__ import annotations

import io
import os
import tempfile

from flask import Flask, jsonify, render_template_string, request, send_file
from pypdf.errors import PyPdfError
from werkzeug.utils import secure_filename

from pdf_handler.pdf_processor import process_pdf_full

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # batas upload 20 MB

# Halaman sementara: form sederhana yang memanggil endpoint lewat fetch().
# Akan diganti dengan templates/index.html di langkah berikutnya.
_TEMP_PAGE = """
<!doctype html>
<meta charset="utf-8">
<title>Vigenere PDF</title>
<body style="font-family:sans-serif;max-width:480px;margin:40px auto">
<h2>Enkripsi / Dekripsi PDF (Vigenere)</h2>
<p><input type="file" id="file" accept="application/pdf"></p>
<p><input type="text" id="key" placeholder="Key" style="width:100%;padding:6px"></p>
<p>
  <button onclick="send('encrypt')">Enkripsi</button>
  <button onclick="send('decrypt')">Dekripsi</button>
</p>
<p id="status"></p>
<script>
async function send(action) {
  const status = document.getElementById('status');
  const file = document.getElementById('file').files[0];
  const key = document.getElementById('key').value;
  if (!file) { status.textContent = 'Pilih file PDF dulu.'; return; }
  const form = new FormData();
  form.append('file', file);
  form.append('key', key);
  status.textContent = 'Memproses...';
  const res = await fetch('/' + action, { method: 'POST', body: form });
  if (!res.ok) {
    let msg = 'Terjadi kesalahan.';
    try { msg = (await res.json()).error; } catch (e) {}
    status.textContent = 'Gagal: ' + msg;
    return;
  }
  const blob = await res.blob();
  const name = (res.headers.get('Content-Disposition') || '').match(/filename="?([^";]+)"?/);
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name ? name[1] : 'hasil.pdf';
  a.click();
  status.textContent = 'Selesai, file terunduh.';
}
</script>
"""


def _error(message: str, status: int):
    return jsonify({"error": message}), status


def _handle(mode: str):
    """Logika bersama untuk /encrypt dan /decrypt."""
    upload = request.files.get("file")
    key = request.form.get("key", "")

    if upload is None or upload.filename == "":
        return _error("File PDF belum dipilih.", 400)
    if not upload.filename.lower().endswith(".pdf"):
        return _error("File harus berformat .pdf.", 400)
    if not key:
        return _error("Key tidak boleh kosong.", 400)

    data = upload.read()
    if not data.startswith(b"%PDF"):
        return _error("Isi file bukan PDF yang valid.", 400)

    stem = os.path.splitext(secure_filename(upload.filename))[0] or "dokumen"
    suffix = "encrypted" if mode == "encrypt" else "decrypted"

    try:
        # File sementara dibuat di folder yang otomatis dihapus setelah selesai
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_path = os.path.join(tmp_dir, "input.pdf")
            out_path = os.path.join(tmp_dir, "output.pdf")
            with open(in_path, "wb") as f:
                f.write(data)

            process_pdf_full(in_path, out_path, key, mode)

            with open(out_path, "rb") as f:
                result = io.BytesIO(f.read())  # baca ke memori sebelum folder dihapus
    except ValueError as e:
        # Salah satunya: mendekripsi PDF yang bukan hasil enkripsi aplikasi ini
        return _error(str(e), 400)
    except PyPdfError:
        return _error("PDF tidak bisa dibaca (rusak atau dilindungi password).", 400)
    except Exception:
        app.logger.exception("Gagal memproses PDF")
        return _error("Terjadi kesalahan saat memproses PDF.", 500)

    return send_file(
        result,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{stem}_{suffix}.pdf",
    )


@app.get("/")
def index():
    return render_template_string(_TEMP_PAGE)


@app.post("/encrypt")
def encrypt():
    return _handle("encrypt")


@app.post("/decrypt")
def decrypt():
    return _handle("decrypt")


@app.errorhandler(413)
def too_large(_):
    return _error("Ukuran file melebihi batas 20 MB.", 413)


if __name__ == "__main__":
    app.run(debug=True)