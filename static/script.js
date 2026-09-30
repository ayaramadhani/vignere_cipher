(() => {
  const $ = id => document.getElementById(id);
  const fileInput = $('file'), keyInput = $('key'), drop = $('drop');
  const encBtn = $('encBtn'), decBtn = $('decBtn');

  // Key dipakai APA ADANYA -- backend (crypto/vigenere.py) menerima huruf
  // besar/kecil dan karakter apa pun, jadi JS di sini TIDAK BOLEH mengubah
  // isi key (dulu ada bug: key difilter jadi huruf A-Z kapital saja,
  // sehingga karakter lain diam-diam hilang sebelum dikirim ke server).
  const fmtSize = n => n >= 1048576 ? (n / 1048576).toFixed(1) + ' MB' : n >= 1024 ? (n / 1024).toFixed(1) + ' KB' : n + ' B';

  function setStatus(text, type = '', tag = 'MENUNGGU', busy = false) {
    $('statusText').textContent = text;
    $('statusBox').className = 'status-box ' + type;
    $('stateTag').textContent = tag;
    $('spin').hidden = !busy;
  }

  function refresh() {
    const key = keyInput.value;
    const hasKey = key.length > 0;
    const hasFile = fileInput.files.length > 0;
    $('keyBadge').className = 'pill' + (hasKey ? '' : ' bad');
    $('keyBadge').innerHTML = `<i></i>${hasKey ? 'KUNCI VALID' : 'KOSONG'}`;
    const ready = hasKey && hasFile;
    encBtn.disabled = decBtn.disabled = !ready;
    if (ready && $('stateTag').textContent === 'MENUNGGU') setStatus('Siap. Pilih Enkripsi atau Dekripsi.', '', 'SIAP');
  }

  function pickFile(f) {
    if (!f) return;
    if (!/\.pdf$/i.test(f.name) && f.type !== 'application/pdf') {
      fileInput.value = ''; drop.classList.remove('has');
      $('fileState').textContent = 'BELUM ADA FILE';
      $('dropTitle').textContent = 'Klik untuk memilih PDF';
      $('dropSub').textContent = 'atau seret dan lepas file ke sini';
      setStatus('File harus berformat PDF. Pilih file dengan ekstensi .pdf.', 'err', 'GAGAL');
      return refresh();
    }
    const dt = new DataTransfer(); dt.items.add(f); fileInput.files = dt.files;
    drop.classList.add('has');
    $('dropTitle').textContent = f.name;
    $('dropSub').textContent = fmtSize(f.size) + ' · klik untuk mengganti';
    $('fileState').textContent = 'FILE DIPILIH';
    setStatus('Masukkan kunci lalu pilih aksi.', '', 'MENUNGGU');
    refresh();
  }

  async function process(action) {
    const file = fileInput.files[0];
    const key = keyInput.value;
    if (!file || !key) return;
    const label = action === 'encrypt' ? 'Mengenkripsi' : 'Mendekripsi';
    encBtn.disabled = decBtn.disabled = true;
    setStatus(`${label} ${file.name}…`, '', 'MEMPROSES', true);

    const fd = new FormData();
    fd.append('file', file);
    fd.append('key', key);

    try {
      const res = await fetch('/' + action, { method: 'POST', body: fd });
      const type = res.headers.get('Content-Type') || '';
      if (!res.ok || type.includes('application/json')) {
        let msg = `Server mengembalikan status ${res.status}.`;
        try { const j = await res.json(); if (j.error) msg = j.error; } catch {}
        throw new Error(msg);
      }
      const blob = await res.blob();
      const cd = res.headers.get('Content-Disposition') || '';
      const m = cd.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
      const base = file.name.replace(/\.pdf$/i, '');
      const name = m ? decodeURIComponent(m[1]) : `${base}_${action === 'encrypt' ? 'encrypted' : 'decrypted'}.pdf`;

      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob); a.download = name; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);

      setStatus(`Selesai. ${name} sudah diunduh.`, 'ok', 'BERHASIL');
    } catch (e) {
      const offline = e instanceof TypeError;
      setStatus(offline ? 'Tidak bisa terhubung ke server. Pastikan app.py masih berjalan.' : e.message, 'err', 'GAGAL');
    } finally {
      refresh();
    }
  }

  fileInput.addEventListener('change', () => pickFile(fileInput.files[0]));
  keyInput.addEventListener('input', refresh);
  encBtn.addEventListener('click', () => process('encrypt'));
  decBtn.addEventListener('click', () => process('decrypt'));
  ['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over'); }));
  ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('over'); }));
  drop.addEventListener('drop', e => pickFile(e.dataTransfer.files[0]));
  refresh();
})();