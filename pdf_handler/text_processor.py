"""
Modul enkripsi TEKS PDF dengan Vigenere ALFABET DINAMIS ("Opsi A").

Masalah yang diselesaikan:
    Vigenere mod 256 menghasilkan kode glyph acak yang hampir semuanya TIDAK
    ada di font subset PDF (mis. font Word), sehingga teks hasil enkripsi
    tampil kosong/kotak. Di sini, enkripsi dilakukan di dalam "alfabet"
    yang terdiri dari kode-kode glyph yang benar-benar dipakai dokumen,
    sehingga hasilnya selalu berupa glyph yang ADA di font -> teks tampil
    sebagai huruf acak.

Rumus (sama dengan Vigenere klasik, hanya alfabetnya berbeda):
    Enkripsi : C = alfabet[ (indeks(P) + K) mod N ]
    Dekripsi : P = alfabet[ (indeks(C) - K) mod N ]
    N = jumlah kode berbeda yang dipakai sebuah font di dokumen.

Detail:
    - Alfabet dibuat PER FONT (kunci: nama BaseFont), karena tiap font
      punya tabel glyph sendiri.
    - Font Type0 dengan encoding Identity-H/V memakai kode 2 byte; font
      lain memakai kode 1 byte.
    - K berasal dari keystream hasil key expansion (SHA-256 counter mode),
      diambil 16 bit per karakter.
    - Alfabet disimpan di metadata PDF hasil enkripsi (/VigenereAlphabet)
      supaya dekripsi memakai alfabet yang persis sama. Alfabet BUKAN
      rahasia; yang rahasia hanya key.
    - Yang diproses hanya teks di content stream halaman (Tj, TJ, ', ").
      Gambar ditangani modul lain (image_processor).
"""

from __future__ import annotations

import hashlib
import json
from typing import Callable, Iterator

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ByteStringObject, TextStringObject

METADATA_KEY = "/VigenereAlphabet"
_TEXT_OPERATORS = {b"Tj", b"'", b'"', b"TJ"}


# ---------------------------------------------------------------- keystream
def _keystream(key: str) -> Iterator[int]:
    """Hasilkan nilai keystream 16-bit tanpa henti dari key (SHA-256 counter
    mode). Deterministik: key sama -> urutan sama."""
    if not key:
        raise ValueError("Key tidak boleh kosong")
    key_bytes = key.encode("utf-8")
    counter = 0
    while True:
        block = hashlib.sha256(key_bytes + b"|text|" + counter.to_bytes(8, "big")).digest()
        for i in range(0, 32, 2):
            yield int.from_bytes(block[i : i + 2], "big")
        counter += 1


# ---------------------------------------------------------------- info font
def _font_info(page, font_name: str | None, cache: dict) -> tuple[str, int]:
    """Kembalikan (kunci_font, ukuran_kode_dalam_byte) untuk font yang sedang
    aktif. Font Type0 + Identity-H/V -> 2 byte; selain itu 1 byte."""
    if font_name in cache:
        return cache[font_name]

    result = ("_unknown|1", 1)
    try:
        resources = page.get("/Resources")
        fonts = resources.get_object().get("/Font") if resources is not None else None
        font_ref = fonts.get_object().get(font_name) if fonts is not None else None
        if font_ref is not None:
            font = font_ref.get_object()
            base = str(font.get("/BaseFont", font_name))
            encoding = font.get("/Encoding")
            if encoding is not None:
                encoding = encoding.get_object() if hasattr(encoding, "get_object") else encoding
            two_byte = font.get("/Subtype") == "/Type0" and str(encoding) in ("/Identity-H", "/Identity-V")
            unit = 2 if two_byte else 1
            result = (f"{base}|{unit}", unit)
    except Exception:
        pass  # font tidak terbaca -> pakai default aman (1 byte)

    cache[font_name] = result
    return result


# ------------------------------------------------------------ penelusuran
def _walk_text(page, content_stream, callback: Callable[[str, int, bytes], bytes | None]) -> None:
    """Telusuri semua string teks di content stream sesuai urutan dokumen.
    callback(kunci_font, unit, bytes_mentah) -> bytes baru (untuk mengganti
    string) atau None (biarkan)."""
    font_name = None
    cache: dict = {}

    def handle(obj):
        raw = obj.original_bytes if hasattr(obj, "original_bytes") else bytes(obj)
        key, unit = _font_info(page, font_name, cache)
        new = callback(key, unit, raw)
        return obj if new is None else ByteStringObject(new)

    for operands, operator in content_stream.operations:
        if operator == b"Tf" and operands:
            font_name = str(operands[0])
        elif operator in (b"Tj", b"'"):
            operands[0] = handle(operands[0])
        elif operator == b'"':
            operands[2] = handle(operands[2])
        elif operator == b"TJ":
            array = operands[0]
            for idx, element in enumerate(array):
                if isinstance(element, (TextStringObject, ByteStringObject)):
                    array[idx] = handle(element)


# ------------------------------------------------------------- inti proses
def _transform_units(raw: bytes, unit: int, alphabet: list[int], index: dict, keystream: Iterator[int], encrypt: bool) -> bytes:
    """Enkripsi/dekripsi satu string: tiap kode (unit byte) digeser di dalam
    alfabet. Keystream SELALU diambil satu nilai per kode (walau kode tidak
    ada di alfabet) supaya urutannya identik saat enkripsi dan dekripsi."""
    n = len(alphabet)
    out = bytearray(raw)
    for pos in range(0, len(raw) - unit + 1, unit):
        code = int.from_bytes(raw[pos : pos + unit], "big")
        k = next(keystream)
        i = index.get(code)
        if i is None or n == 0:
            continue
        j = (i + k) % n if encrypt else (i - k) % n
        out[pos : pos + unit] = alphabet[j].to_bytes(unit, "big")
    return bytes(out)


def process_pdf_text(input_path: str, output_path: str, key: str, mode: str = "encrypt") -> None:
    """Enkripsi/dekripsi teks PDF dengan Vigenere alfabet dinamis.

    Args:
        input_path: PDF sumber.
        output_path: PDF hasil.
        key: kata kunci.
        mode: "encrypt" atau "decrypt".

    Raises:
        ValueError: mode salah, key kosong, atau (saat decrypt) PDF tidak
            memiliki alfabet (bukan hasil enkripsi modul ini).
    """
    if mode not in ("encrypt", "decrypt"):
        raise ValueError('mode harus "encrypt" atau "decrypt"')
    if not key:
        raise ValueError("Key tidak boleh kosong")
    encrypt = mode == "encrypt"

    reader = PdfReader(input_path)
    writer = PdfWriter()
    writer.append(reader)

    # --- Tahap 1: siapkan alfabet per font
    if encrypt:
        collected: dict[str, set[int]] = {}

        def collect(font_key: str, unit: int, raw: bytes):
            bucket = collected.setdefault(font_key, set())
            for pos in range(0, len(raw) - unit + 1, unit):
                bucket.add(int.from_bytes(raw[pos : pos + unit], "big"))
            return None

        for page in writer.pages:
            cs = page.get_contents()
            if cs is not None:
                _walk_text(page, cs, collect)
        alphabets = {font_key: sorted(codes) for font_key, codes in collected.items()}
    else:
        stored = (reader.metadata or {}).get(METADATA_KEY)
        if not stored:
            raise ValueError("PDF ini tidak punya alfabet (/VigenereAlphabet): bukan hasil enkripsi modul ini")
        alphabets = json.loads(stored)

    indexes = {font_key: {code: i for i, code in enumerate(alpha)} for font_key, alpha in alphabets.items()}

    # --- Tahap 2: enkripsi/dekripsi string teks
    keystream = _keystream(key)

    def transform(font_key: str, unit: int, raw: bytes):
        alphabet = alphabets.get(font_key, [])
        return _transform_units(raw, unit, alphabet, indexes.get(font_key, {}), keystream, encrypt)

    for page in writer.pages:
        cs = page.get_contents()
        if cs is not None:
            _walk_text(page, cs, transform)
            page.replace_contents(cs)

    if encrypt:
        writer.add_metadata({METADATA_KEY: json.dumps(alphabets)})

    with open(output_path, "wb") as f:
        writer.write(f)


if __name__ == "__main__":
    # Jalankan dari folder root proyek:
    #     python -m pdf_handler.text_processor contoh.pdf KUNCI123
    # Hasil:
    #     contoh_text_encrypted.pdf  (teks tampil sebagai HURUF ACAK)
    #     contoh_text_decrypted.pdf  (teks kembali normal)
    import sys

    if len(sys.argv) != 3:
        print("Cara pakai: python -m pdf_handler.text_processor <file.pdf> <key>")
        sys.exit(1)

    input_pdf, test_key = sys.argv[1], sys.argv[2]
    base = input_pdf.rsplit(".", 1)[0]
    enc_path, dec_path = f"{base}_text_encrypted.pdf", f"{base}_text_decrypted.pdf"

    print(f"Mengenkripsi teks '{input_pdf}' -> '{enc_path}' ...")
    process_pdf_text(input_pdf, enc_path, test_key, "encrypt")
    print("Selesai. Buka file ini: teks harus tampil sebagai huruf acak.\n")

    print(f"Mendekripsi '{enc_path}' -> '{dec_path}' ...")
    process_pdf_text(enc_path, dec_path, test_key, "decrypt")
    print("Selesai. Teks pada file ini harus kembali normal.")