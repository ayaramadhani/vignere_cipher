"""
Modul untuk memproses gambar (XObject Image) di dalam PDF: mengenkripsi/
mendekripsi data PIKSEL gambar dengan Vigenere cipher, sehingga hasilnya
tetap berupa gambar yang valid (bisa ditampilkan PDF reader), tapi isinya
noise/acak -- bukan ikon "gambar rusak".

Alur kerja:
    1. Baca gambar dari XObject sebagai piksel mentah (lewat Pillow, via
       pypdf `page.images`), BUKAN byte JPEG/PNG terkompresinya.
    2. Enkripsi/dekripsi piksel mentah itu dengan Vigenere (mod 256).
    3. Simpan kembali sebagai stream dengan filter /FlateDecode (lossless),
       BUKAN /DCTDecode (JPEG, lossy).

Kenapa harus /FlateDecode, bukan JPEG:
    JPEG itu lossy -- setiap kali data di-encode ulang jadi JPEG, sebagian
    presisi piksel hilang. Kalau gambar terenkripsi disimpan sebagai JPEG,
    proses dekripsi TIDAK akan mengembalikan piksel yang 100% sama dengan
    aslinya (gambar hasil dekripsi jadi rusak/tidak identik). FlateDecode
    adalah kompresi lossless (mirip ZIP), jadi piksel yang disimpan dan
    dibaca kembali dijamin identik bit-per-bit -- wajib untuk cipher yang
    butuh dekripsi presisi seperti Vigenere.

Catatan penting soal hasil visual:
    Vigenere cipher menambahkan key yang BERULANG ke tiap byte. Untuk
    gambar dengan area warna yang berubah perlahan (gradasi), pola
    perulangan key ini masih bisa terlihat samar sebagai garis/pita
    vertikal di hasil enkripsi -- BUKAN noise total seperti cipher modern
    (AES dkk). Ini justru kelemahan Vigenere yang baik untuk dibahas di
    laporan/analisis keamanan tugas kamu.
"""

from __future__ import annotations

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject

from crypto.vigenere import vigenere_decrypt_bytes, vigenere_encrypt_bytes


def _process_page_images(page, key: str, mode: str) -> None:
    """Enkripsi/dekripsi semua gambar (XObject) pada satu halaman, in-place.

    `page` harus berasal dari PdfWriter (bukan PdfReader), karena kita
    memodifikasi objek stream-nya secara langsung.
    """
    transform = vigenere_encrypt_bytes if mode == "encrypt" else vigenere_decrypt_bytes

    for image_file in page.images:
        # Ambil objek stream XObject yang sesungguhnya (bukan wrapper ImageFile)
        stream_obj = image_file.indirect_reference.get_object()

        # Ambil piksel MENTAH (sudah didecode dari JPEG/format aslinya oleh Pillow)
        raw_pixels = image_file.image.tobytes()
        processed = transform(raw_pixels, key)

        # Ganti filter jadi FlateDecode (lossless) -- WAJIB, supaya piksel
        # tersimpan presisi dan bisa didekripsi dengan benar nantinya.
        stream_obj[NameObject("/Filter")] = NameObject("/FlateDecode")
        if "/DecodeParms" in stream_obj:
            del stream_obj[NameObject("/DecodeParms")]

        # set_data() menerima piksel MENTAH (bukan yang sudah di-compress
        # manual) -- EncodedStreamObject akan meng-compress-nya sendiri.
        stream_obj.set_data(processed)


def process_pdf_images(input_path: str, output_path: str, key: str, mode: str = "encrypt") -> None:
    """Proses (enkripsi/dekripsi) semua gambar pada seluruh halaman PDF.

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
    writer.append(reader)  # append (bukan add_page satu-satu) supaya semua
                            # halaman + resource gambar ikut disalin utuh

    for page in writer.pages:
        _process_page_images(page, key, mode)

    with open(output_path, "wb") as f:
        writer.write(f)


if __name__ == "__main__":
    # --- Kode uji cepat, jalankan dengan:
    #     python -m pdf_handler.image_processor contoh_gambar.pdf KUNCI123
    # Catatan: contoh_gambar.pdf harus PDF yang MENGANDUNG GAMBAR.
    # akan menghasilkan:
    #     contoh_gambar_encrypted.pdf  (gambar harus tampil sebagai noise/acak)
    #     contoh_gambar_decrypted.pdf  (gambar harus identik dgn aslinya)

    import sys

    if len(sys.argv) != 3:
        print("Cara pakai: python -m pdf_handler.image_processor <file.pdf> <key>")
        sys.exit(1)

    input_pdf = sys.argv[1]
    test_key = sys.argv[2]

    base = input_pdf.rsplit(".", 1)[0]
    encrypted_path = f"{base}_encrypted.pdf"
    decrypted_path = f"{base}_decrypted.pdf"

    print(f"Mengenkripsi gambar di '{input_pdf}' -> '{encrypted_path}' ...")
    process_pdf_images(input_pdf, encrypted_path, test_key, mode="encrypt")
    print("Selesai. Buka file ini -- gambar harus tampil sebagai noise acak,")
    print("bukan ikon 'gambar rusak' dan bukan gambar aslinya.")
    print()

    print(f"Mendekripsi gambar di '{encrypted_path}' -> '{decrypted_path}' ...")
    process_pdf_images(encrypted_path, decrypted_path, test_key, mode="decrypt")
    print("Selesai. Gambar pada file ini harus identik dengan gambar aslinya.")