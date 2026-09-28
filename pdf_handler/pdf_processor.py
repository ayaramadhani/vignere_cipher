"""
Modul gabungan: mengenkripsi/mendekripsi TEKS dan GAMBAR sebuah PDF dalam
satu kali panggilan, menghasilkan SATU file output.

Modul ini tidak menulis ulang logika enkripsi, hanya menjalankan dua modul
yang sudah kamu uji secara berurutan:
    - pdf_handler.text_processor.process_pdf_text    (teks, alfabet dinamis)
    - pdf_handler.image_processor.process_pdf_images (gambar, level piksel)

URUTAN PENTING (karena alfabet teks disimpan di metadata PDF):
    ENKRIPSI : gambar dulu -> teks terakhir
               (teks menulis metadata alfabet di langkah terakhir, supaya
               tidak hilang ketika file ditulis ulang)
    DEKRIPSI : teks dulu -> gambar terakhir
               (teks perlu membaca metadata alfabet dari PDF terenkripsi)

File perantara disimpan di folder sementara dan otomatis dihapus.
"""

from __future__ import annotations

import os
import tempfile

from pdf_handler.image_processor import process_pdf_images
from pdf_handler.text_processor import process_pdf_text


def process_pdf_full(input_path: str, output_path: str, key: str, mode: str = "encrypt") -> None:
    """Proses teks + gambar PDF sekaligus, simpan ke satu file output.

    Args:
        input_path: path file PDF sumber.
        output_path: path file PDF hasil proses (akan dibuat/ditimpa).
        key: kata kunci Vigenere.
        mode: "encrypt" atau "decrypt".

    Raises:
        ValueError: jika mode salah, key kosong, atau (saat decrypt) PDF
            bukan hasil enkripsi aplikasi ini.
    """
    if mode not in ("encrypt", "decrypt"):
        raise ValueError('mode harus "encrypt" atau "decrypt"')
    if not key:
        raise ValueError("Key tidak boleh kosong")

    with tempfile.TemporaryDirectory() as tmp_dir:
        middle = os.path.join(tmp_dir, "middle.pdf")

        if mode == "encrypt":
            process_pdf_images(input_path, middle, key, "encrypt")
            process_pdf_text(middle, output_path, key, "encrypt")
        else:
            process_pdf_text(input_path, middle, key, "decrypt")
            process_pdf_images(middle, output_path, key, "decrypt")


if __name__ == "__main__":
    # Jalankan dari folder root proyek:
    #     python -m pdf_handler.pdf_processor contoh.pdf KUNCI123
    # Hasil:
    #     contoh_full_encrypted.pdf  (teks acak + gambar noise)
    #     contoh_full_decrypted.pdf  (kembali seperti aslinya)
    import sys

    if len(sys.argv) != 3:
        print("Cara pakai: python -m pdf_handler.pdf_processor <file.pdf> <key>")
        sys.exit(1)

    input_pdf, test_key = sys.argv[1], sys.argv[2]
    base = input_pdf.rsplit(".", 1)[0]
    enc_path, dec_path = f"{base}_full_encrypted.pdf", f"{base}_full_decrypted.pdf"

    print(f"Mengenkripsi teks + gambar '{input_pdf}' -> '{enc_path}' ...")
    process_pdf_full(input_pdf, enc_path, test_key, "encrypt")
    print("Selesai. Buka file ini: teks harus huruf acak DAN gambar harus noise.\n")

    print(f"Mendekripsi '{enc_path}' -> '{dec_path}' ...")
    process_pdf_full(enc_path, dec_path, test_key, "decrypt")
    print("Selesai. File ini harus kembali seperti PDF aslinya.")