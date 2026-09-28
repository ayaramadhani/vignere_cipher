"""
Modul Vigenere Cipher level byte (mod 256), dengan KEY EXPANSION.

Rumus dasar Vigenere tetap dipakai (untuk tiap byte P pada posisi i, dengan
byte keystream K_i):
    Enkripsi : C_i = (P_i + K_i) mod 256
    Dekripsi : P_i = (C_i - K_i) mod 256

Bedanya dengan Vigenere "murni": pada Vigenere klasik, K_i = key[i % len(key)]
-- yaitu key pendek diulang-ulang langsung. Kalau key-nya pendek (misal 8
karakter) dan datanya berisi banyak byte yang NILAINYA SAMA/mirip berulang
(kasus umum pada gambar dengan area warna solid, seperti screenshot), pola
perulangan key ini masih bisa "kebayang" di hasil enkripsi -- background
cuma bergeser warna secara konsisten, bukan berubah jadi noise acak.

Solusi di modul ini: KEY EXPANSION. Key pendek yang dimasukkan pengguna
diperluas dulu jadi KEYSTREAM sepanjang data yang akan dienkripsi, memakai
fungsi hash SHA-256 sebagai pembangkit byte pseudo-acak (counter mode):

    keystream = SHA256(key || counter=0) || SHA256(key || counter=1) || ...

Prinsip inti Vigenere (penjumlahan modulo dengan sebuah keystream yang
diturunkan dari kata kunci) TETAP SAMA -- ini sering disebut "Extended
Vigenere Cipher" di literatur/tugas kuliah kriptografi. Bedanya cuma
sumber keystream-nya, bukan operasi enkripsinya.

Konsekuensi: keystream sepanjang data itu sendiri PRAKTIS TIDAK BERULANG
untuk ukuran file yang wajar (SHA-256 keluarannya sangat sensitif terhadap
perubahan counter), sehingga pola berulang pada plaintext (seperti area
gambar berwarna solid) tidak lagi menghasilkan pola berulang yang sama
pada ciphertext.
"""

from __future__ import annotations

import hashlib


def _validate_key(key: str) -> bytes:
    """Validasi dan ubah key (string) menjadi bytes.

    Raises:
        ValueError: jika key kosong.
    """
    if not key:
        raise ValueError("Key tidak boleh kosong")

    # encode sebagai UTF-8 supaya key boleh berisi karakter apa saja,
    # bukan cuma huruf A-Z seperti Vigenere klasik
    return key.encode("utf-8")


def _expand_key(key: str, length: int) -> bytes:
    """Perluas key pendek jadi keystream sepanjang `length` byte, pakai
    SHA-256 counter mode sebagai pembangkit byte pseudo-acak.

    Args:
        key: kata kunci asli yang dimasukkan pengguna.
        length: panjang keystream yang dibutuhkan (harus sama dengan
            panjang data yang akan dienkripsi/didekripsi).

    Returns:
        bytes keystream sepanjang `length`, deterministik terhadap key
        (key yang sama akan selalu menghasilkan keystream yang sama --
        ini WAJIB supaya dekripsi bisa mengembalikan keystream yang
        identik dengan yang dipakai saat enkripsi).
    """
    key_bytes = _validate_key(key)
    keystream = bytearray()

    counter = 0
    while len(keystream) < length:
        # SHA-256 menghasilkan 32 byte per pemanggilan; counter (4 byte,
        # big-endian) digabung ke key supaya tiap blok hash-nya berbeda
        block = hashlib.sha256(key_bytes + counter.to_bytes(4, "big")).digest()
        keystream.extend(block)
        counter += 1

    return bytes(keystream[:length])


def vigenere_encrypt_bytes(data: bytes, key: str) -> bytes:
    """Enkripsi data biner menggunakan Vigenere cipher level byte (mod 256)
    dengan keystream hasil key expansion.

    Args:
        data: data mentah yang akan dienkripsi (misal isi stream PDF).
        key: kata kunci (string, bebas karakter apa saja, tidak boleh kosong).

    Returns:
        bytes hasil enkripsi, dengan panjang yang SAMA PERSIS dengan data asli.
        Ini penting untuk kasus PDF: karena panjang byte tidak berubah, field
        /Length pada dictionary objek PDF tidak perlu diubah.
    """
    keystream = _expand_key(key, len(data))

    output = bytearray(len(data))
    for i, byte in enumerate(data):
        output[i] = (byte + keystream[i]) % 256

    return bytes(output)


def vigenere_decrypt_bytes(data: bytes, key: str) -> bytes:
    """Dekripsi data biner hasil vigenere_encrypt_bytes.

    Args:
        data: data terenkripsi.
        key: kata kunci yang SAMA dengan yang dipakai saat enkripsi.

    Returns:
        bytes hasil dekripsi (harus identik dengan data asli sebelum dienkripsi).
    """
    keystream = _expand_key(key, len(data))

    output = bytearray(len(data))
    for i, byte in enumerate(data):
        output[i] = (byte - keystream[i]) % 256

    return bytes(output)


if __name__ == "__main__":
    # --- Kode uji cepat, jalankan langsung dengan:
    #     python crypto/vigenere.py
    # untuk memastikan logika enkripsi/dekripsi benar sebelum dipakai di PDF.

    contoh_data = "Ini contoh teks & data biner apa saja \x00\x01\xff".encode("utf-8", errors="ignore")
    kunci_uji = "KUNCI123"

    terenkripsi = vigenere_encrypt_bytes(contoh_data, kunci_uji)
    terdekripsi = vigenere_decrypt_bytes(terenkripsi, kunci_uji)

    print("Data asli      :", contoh_data)
    print("Terenkripsi    :", terenkripsi)
    print("Hasil dekripsi :", terdekripsi)
    print()

    if terdekripsi == contoh_data:
        print("BERHASIL: hasil dekripsi identik dengan data asli.")
    else:
        print("GAGAL: ada perbedaan antara data asli dan hasil dekripsi.")

    # Uji tambahan: pastikan panjang data tidak berubah (penting untuk PDF)
    assert len(contoh_data) == len(terenkripsi) == len(terdekripsi), (
        "Panjang data berubah! Ini akan bermasalah untuk field /Length di PDF."
    )
    print("BERHASIL: panjang byte sebelum dan sesudah enkripsi identik.")

    # Uji tambahan: buktikan keystream TIDAK berulang pendek seperti
    # Vigenere klasik -- ambil data konstan (banyak byte sama, mirip
    # kasus background gambar solid), pastikan hasil enkripsinya TIDAK
    # berpola berulang pendek.
    print()
    print("--- Uji key expansion pada data konstan (simulasi background solid) ---")
    data_konstan = bytes([100]) * 64  # 64 byte bernilai 100 semua
    hasil = vigenere_encrypt_bytes(data_konstan, kunci_uji)
    print("Data konstan (64 byte nilai 100) dienkripsi jadi:")
    print(hasil.hex())
    # Cek apakah ada pola berulang pendek (periode <= 16 byte)
    periode_terdeteksi = None
    for p in range(1, 17):
        if all(hasil[i] == hasil[i % p] for i in range(len(hasil))):
            periode_terdeteksi = p
            break
    if periode_terdeteksi:
        print(f"PERINGATAN: masih terdeteksi pola berulang tiap {periode_terdeteksi} byte.")
    else:
        print("BERHASIL: tidak ada pola berulang pendek (<=16 byte) terdeteksi.")