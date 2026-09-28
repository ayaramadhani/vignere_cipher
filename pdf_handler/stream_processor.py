"""
Modul untuk memproses file PDF: membaca content stream tiap halaman,
mengenkripsi/mendekripsi HANYA string teks di dalamnya dengan Vigenere
cipher, lalu menulis ulang PDF dengan struktur (header, xref, trailer)
dan operator PDF lain (BT, ET, Tf, Tm, dst) tetap utuh.

Pendekatan ini ("Opsi A - enkripsi selektif") membuat PDF hasil enkripsi:
- TETAP BISA DIBUKA oleh PDF reader (tidak error/corrupt)
- Teksnya TAMPIL sebagai karakter/glyph acak (bukan halaman kosong),
  karena operator perintah render (BT/ET/Tf/Tm) tetap dikenali reader,
  cuma ISI STRING yang ditampilkannya yang sudah diacak.

Operator PDF yang menampilkan teks dan ditangani di sini:
    Tj   -> menampilkan satu string:            (teks) Tj
    '    -> pindah baris lalu tampilkan string:  (teks) '
    "    -> set spasi kata/karakter lalu tampilkan: aw ac (teks) "
    TJ   -> menampilkan array string+angka kerning: [(teks) -120 (lagi)] TJ

Catatan penting:
- pypdf otomatis melakukan decompress/compress ulang (misal FlateDecode)
  saat content stream dibaca/ditulis lewat get_contents()/replace_contents(),
  jadi kita tidak perlu urus zlib manual.
- Tahap ini BARU menangani teks. Data mentah gambar (XObject Image)
  BELUM ditangani -- itu jadi tahap lanjutan berikutnya.
"""

from __future__ import annotations

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ByteStringObject, TextStringObject

from crypto.vigenere import vigenere_decrypt_bytes, vigenere_encrypt_bytes

# Operator PDF yang operand-nya berisi string yang ditampilkan ke halaman
_TEXT_SHOWING_OPERATORS = {b"Tj", b"'", b'"', b"TJ"}


def _transform_string_operand(string_obj, key: str, mode: str) -> ByteStringObject:
    """Enkripsi/dekripsi satu operand string PDF, kembalikan sebagai
    ByteStringObject (ditulis sebagai hex string <...> di PDF, sehingga
    bisa menampung byte hasil enkripsi yang nilainya acak/bukan teks valid).
    """
    # original_bytes mengambil representasi byte PDF yang sesungguhnya
    # (bukan representasi Python str-nya) -- penting supaya encoding
    # karakter khusus tidak salah diterjemahkan sebelum dienkripsi.
    raw = string_obj.original_bytes if hasattr(string_obj, "original_bytes") else bytes(string_obj)

    transform = vigenere_encrypt_bytes if mode == "encrypt" else vigenere_decrypt_bytes
    return ByteStringObject(transform(raw, key))


def _process_content_stream(content_stream, key: str, mode: str) -> None:
    """Modifikasi in-place setiap operand string pada operator penampil teks
    di dalam ContentStream yang sudah di-parse oleh pypdf.
    """
    for operands, operator in content_stream.operations:
        if operator not in _TEXT_SHOWING_OPERATORS:
            continue

        if operator == b"Tj" or operator == b"'":
            operands[0] = _transform_string_operand(operands[0], key, mode)

        elif operator == b'"':
            # operand ke-2 (index 2) adalah string-nya; index 0 & 1 adalah
            # angka spasi kata/karakter (aw, ac), bukan bagian dari teks
            operands[2] = _transform_string_operand(operands[2], key, mode)

        elif operator == b"TJ":
            # operand tunggal berupa ArrayObject berisi campuran string
            # (teks yang ditampilkan) dan angka (kerning/pergeseran posisi
            # antar glyph) -- cuma elemen string yang diproses
            array = operands[0]
            for idx, element in enumerate(array):
                if isinstance(element, (TextStringObject, ByteStringObject)):
                    array[idx] = _transform_string_operand(element, key, mode)


def process_pdf(input_path: str, output_path: str, key: str, mode: str = "encrypt") -> None:
    """Proses (enkripsi/dekripsi) string teks pada setiap halaman PDF.

    Args:
        input_path: path file PDF sumber.
        output_path: path file PDF hasil proses (akan dibuat/ditimpa).
        key: kata kunci Vigenere.
        mode: "encrypt" atau "decrypt".

    Raises:
        ValueError: jika mode bukan "encrypt" atau "decrypt".
    """
    if mode not in ("encrypt", "decrypt"):
        raise ValueError('mode harus "encrypt" atau "decrypt"')

    reader = PdfReader(input_path)
    writer = PdfWriter()

    for page in reader.pages:
        content_stream = page.get_contents()

        if content_stream is not None:
            _process_content_stream(content_stream, key, mode)
            # replace_contents menerima objek ContentStream secara langsung;
            # pypdf akan menghitung ulang /Length secara otomatis saat ditulis.
            page.replace_contents(content_stream)

        writer.add_page(page)

    with open(output_path, "wb") as f:
        writer.write(f)


if __name__ == "__main__":
    # --- Kode uji cepat, jalankan dengan:
    #     python -m pdf_handler.stream_processor contoh.pdf KUNCI123
    # akan menghasilkan:
    #     contoh_encrypted.pdf  (harus tetap kebuka, teks tampil ACAK)
    #     contoh_decrypted.pdf  (teks harus kembali NORMAL seperti aslinya)

    import sys

    if len(sys.argv) != 3:
        print("Cara pakai: python -m pdf_handler.stream_processor <file.pdf> <key>")
        sys.exit(1)

    input_pdf = sys.argv[1]
    test_key = sys.argv[2]

    base = input_pdf.rsplit(".", 1)[0]
    encrypted_path = f"{base}_encrypted.pdf"
    decrypted_path = f"{base}_decrypted.pdf"

    print(f"Mengenkripsi '{input_pdf}' -> '{encrypted_path}' ...")
    process_pdf(input_pdf, encrypted_path, test_key, mode="encrypt")
    print("Selesai. Buka file ini di PDF reader -- harus tetap kebuka,")
    print("dengan teks tampil sebagai karakter acak (bukan halaman kosong).")
    print()

    print(f"Mendekripsi '{encrypted_path}' -> '{decrypted_path}' ...")
    process_pdf(encrypted_path, decrypted_path, test_key, mode="decrypt")
    print("Selesai. Teks pada file ini harus kembali normal seperti aslinya.")