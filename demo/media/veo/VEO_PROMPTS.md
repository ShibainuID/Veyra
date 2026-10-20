# Video demo Veyra dengan Google Veo

Dua video berjalan **paralel di timeline yang sama**:

- **Video A, kamera HP (vertikal 9:16).** Operator merekam sapi di zona scan: moncong → gigi → badan samping dengan marker, lalu sapi dilepas.
- **Video B, CCTV (horizontal 16:9).** Kamera tetap di dinding samping yang tinggi, melihat kandang dari atas. Di detik yang sama terlihat operator dan sapi yang sama di zona scan, lalu sapi berjalan masuk ke kandang dan diikuti tracker.

Di editor, kedua video diletakkan berdampingan. Video B nanti juga dijalankan lewat tracker asli kita (`calf_detector_v1` + BoT-SORT), dan Video A lewat worker enrollment.

> Semua footage ini buatan AI. Di demo dan pitch harus diberi label **"simulated (AI-generated)"**, sesuai aturan PRD soal label sumber.

---

## 1. Gambar referensi (dari dataset training kita)

Folder `references/`:

| File | Sumber | Dipakai untuk |
| --- | --- | --- |
| `01_barn_cctv_wide.png` | 8-Calves (Fang et al. 2025, CC BY 4.0), frame CCTV kandang asli | Gaya dan sudut CCTV, bentuk kandang: alas jerami, dinding panel, palung pakan, gerbang besi di bawah |
| `02_barn_cctv_alt.png` | 8-Calves | Variasi pencahayaan dan posisi sapi |
| `03_barn_cctv_scan_zone.png` | 8-Calves + kotak kuning yang saya gambar | Posisi **zona scan** (persegi kuning di lantai, dekat gerbang) |
| `04_body_side_framing.jpg` | R11 Mendeley (Bai 2025, CC BY 4.0) | **Hanya framing** view badan samping (seluruh badan masuk frame, kamera sejajar). Warna sapinya beda, jangan dipakai untuk penampilan sapi |
| `05_muzzle_closeup.jpg` | Li et al. 2022 (Zenodo, CC BY 4.0) | Framing dan tekstur close-up moncong gelap |
| `06_aruco_marker_id7.png` | Dibuat dengan OpenCV (DICT_4X4_50, id 7) | Ditempel di kartu putih saat pasca-produksi (lihat bagian 6) |

**Kenapa Holstein (hitam-putih) di kandang jerami:** detektor CCTV kita dilatih di kandang 8-Calves dengan sapi Holstein. Kalau video Veo mirip kandang itu, tracker kita bisa memproses Video B dengan baik. Dataset R11 (sapi coklat, lahan terbuka) hanya dipakai untuk framing.

---

## 2. Karakter yang harus konsisten di semua shot

Tempel blok ini (bahasa Inggris) di **setiap** prompt supaya sapi dan orangnya tidak berubah antar-shot dan antar-kamera.

```text
HERO ANIMAL: a young Holstein-Friesian heifer, about 12 months old, black-and-white coat; a large white star on the
forehead, a black patch around the left eye, a mostly black left flank with one large irregular white patch, white
lower legs on all four legs, a dark black muzzle, wearing a plain red rope halter. No ear tags on any animal.
PEOPLE: OPERATOR, a farm worker in dark green overalls and black rubber boots, holding a smartphone;
HELPER, a farm worker in a navy work jacket, blue jeans and rubber boots, holding the halter lead.
SETTING: an indoor calf and heifer barn with deep golden straw bedding, grey metal panel walls, a hay rack on the
left, a steel gate along the bottom; a yellow-painted rectangular SCAN ZONE on the concrete floor just inside the gate.
Soft daylight from a high window, no music, natural barn ambience.
```

---

## 3. Timeline sinkron (4 shot × 8 detik = 32 detik)

| Waktu | Video A, HP (9:16) | Video B, CCTV (16:9) |
| --- | --- | --- |
| 0–8 d | **A1 Moncong.** HP mendekat; moncong memenuhi frame dan diam 3 detik | **B1.** Kandang dengan 5–6 heifer; hero heifer berdiri di zona scan kuning, HELPER memegang halter, OPERATOR membungkuk ke arah hidung sapi dengan HP |
| 8–16 d | **A2 Gigi.** HELPER membuka bibir bawah, gigi seri bawah terlihat | **B2.** Posisi sama; HELPER di kepala sapi, OPERATOR tetap di depan |
| 16–24 d | **A3 Badan.** Operator mundur ke samping; seluruh badan masuk frame, HELPER menempelkan kartu putih persegi di sisi badan | **B3.** OPERATOR mundur ke samping sapi; HELPER berdiri di sisi badan sapi memegang kartu |
| 24–32 d | **A4 Lepas.** Halter dilepas; heifer berjalan masuk kandang | **B4.** Heifer keluar dari zona scan dan bergabung dengan heifer lain; kedua orang keluar lewat gerbang |

Saat ingest ke backend, **waktu scan = detik ~4** (moncong terekam) dipakai sebagai `scanned_at` di `POST /cameras/{id}/scans`, dengan `started_at` rekaman CCTV = detik 0 di timeline yang sama.

---

## 4. Alur kerja di Veo (supaya konsisten)

Fitur dan nama menu Veo berubah antar-versi. Cek yang tersedia di versimu: *reference images / ingredients*, *first frame / frames-to-video*, dan *extend*.

1. **Buat keyframe dulu dengan model gambar** (mis. Imagen atau Gemini image di Flow), memakai prompt di bagian 5.1:
   - `K_cctv`: keyframe CCTV, referensi `01` + `03`.
   - `K_hero`: potret hero heifer di zona scan dari setinggi mata, referensi `04` untuk framing.
2. **Video B (CCTV):** B1 = *first frame* `K_cctv` + prompt B1. B2–B4 = **extend** dari frame terakhir shot sebelumnya, supaya kamera dan kandangnya identik.
3. **Video A (HP):** A1 = *reference/ingredient* `K_hero` + `05` + prompt A1. A2–A4 = **extend** berturut-turut.
4. Kalau ada shot yang meleset (sapi berubah corak, orang bertambah), generate ulang shot itu saja. Jangan teruskan extend dari shot yang salah.

Pengaturan: 16:9 untuk CCTV, 9:16 untuk HP, durasi 8 detik per shot, audio boleh nyala (suara kandang). **Jangan minta teks atau UI di video**: tulisan dari Veo biasanya rusak. Timestamp CCTV dan UI aplikasi ditambahkan saat pasca-produksi.

---

## 5. Prompt

### 5.1 Keyframe (model gambar)

**K_cctv**

```text
Still frame from a fixed security camera mounted high on the side wall of an indoor heifer barn, looking down at a
steep angle over the whole pen, wide-angle lens with slight barrel distortion, slightly washed-out CCTV colours,
800x600 security-camera look. Deep golden straw bedding, grey metal panel walls, a hay rack on the left, a steel gate
along the bottom edge. Five young Holstein-Friesian heifers spread around the pen. Near the bottom centre, just
inside the gate, a yellow-painted rectangular scan zone on the concrete floor; the HERO ANIMAL stands inside it,
HELPER holds its red halter, OPERATOR bends towards its nose holding a smartphone. [paste the HERO/PEOPLE/SETTING
block]. Match the camera angle, pen layout and lighting of the reference images. No text, no timestamp, no logos.
```

**K_hero**

```text
Eye-level photo inside the same straw barn: the HERO ANIMAL standing calmly in the yellow scan zone, whole body visible
from the left side, camera level with the middle of the body, HELPER at its head holding the red halter.
[paste the HERO/PEOPLE/SETTING block]. Use the reference only for framing (full side view, level camera);
the animal must be a black-and-white Holstein heifer. Natural daylight, sharp focus, no text.
```

### 5.2 Video A: HP (9:16, handheld)

**A1: moncong (0–8 d)**

```text
Vertical smartphone video, handheld by the OPERATOR, first-person view. The camera moves slowly towards the HERO
ANIMAL's face as it stands in the scan zone, then frames its dark black muzzle so it fills about 90% of the frame,
straight on, centred, sharp focus on the nostrils and the beaded skin texture of the muzzle, and holds steady for
three seconds. The heifer breathes calmly; slight natural hand shake. [paste block]. Close-up texture like the muzzle
reference. No text or on-screen interface.
```

**A2: gigi (8–16 d)**

```text
Continue the same vertical handheld smartphone shot. The HELPER gently folds down the heifer's lower lip with a gloved
hand, revealing its lower front incisor teeth; the camera holds a steady, well-lit close-up of the lower incisors and
gums for three seconds, then the HELPER releases the lip. Calm animal, careful handling. [paste block]. No text.
```

**A3: badan samping (16–24 d)**

```text
Continue the same vertical handheld smartphone shot. The OPERATOR walks backwards to the left side of the HERO ANIMAL
until the whole body, from nose to tail and hooves to back, fits in the frame, camera held level at mid-body height,
roughly perpendicular to the animal. The HELPER holds a flat plain white square card, about the size of a sheet of
paper, pressed flat against the heifer's flank behind the shoulder, facing the camera. The heifer stands square and
still for three seconds. [paste block]. No text, the card is plain white.
```

**A4: dilepas (24–32 d)**

```text
Continue the same vertical handheld smartphone shot. The HELPER unclips the red halter lead; the HERO ANIMAL steps out
of the yellow scan zone and walks calmly into the straw pen towards the other heifers. The camera follows it briefly,
then stops. [paste block]. No text.
```

### 5.3 Video B: CCTV (16:9, kamera diam)

Awali **setiap** prompt CCTV dengan kalimat ini:

```text
Fixed security camera high on the side wall, looking down over the whole pen at a steep angle, wide-angle lens with
slight barrel distortion, washed-out CCTV colours, the camera never moves, no zoom, no cuts. [paste block]
```

**B1 (0–8 d)**

```text
Five young Holstein heifers rest and walk slowly on the straw. In the yellow scan zone near the gate, the HERO ANIMAL
stands still; the HELPER holds its red halter, the OPERATOR leans in close to its nose holding a smartphone up to the
muzzle. Other heifers keep their distance from the scan zone. No text or timestamp.
```

**B2 (8–16 d)**

```text
Same fixed camera and scene, continuous action. In the scan zone the HELPER bends at the heifer's head handling its
mouth while the OPERATOR keeps the phone close to the head. The other heifers move slowly around the pen. No text.
```

**B3 (16–24 d)**

```text
Same fixed camera and scene, continuous action. The OPERATOR steps back to the left side of the heifer and holds the
phone up towards its body; the HELPER stands at the heifer's flank holding a small white card against its side.
The heifer stays inside the scan zone. No text.
```

**B4 (24–32 d)**

```text
Same fixed camera and scene, continuous action. The HELPER releases the halter; the HERO ANIMAL walks out of the
yellow scan zone into the middle of the pen and joins the other heifers, clearly separated from them while walking.
Both people leave through the steel gate. The heifers spread out across the straw. No text.
```

### 5.4 Opsional: visual untuk alert pergerakan (B5, 8 d)

Hanya sebagai ilustrasi di layar alert. Datanya tetap dari replay `anomaly` yang berlabel `simulated`, karena 8 detik video tidak bisa membuktikan pergerakan berkurang selama berjam-jam.

```text
Same fixed security camera and pen, later in the day. The HERO ANIMAL lies alone in the back right corner on the straw,
head low, barely moving, while the other heifers walk around and feed at the hay rack. No text.
```

### Negative prompt (kalau tersedia)

```text
text, subtitles, watermark, logo, user interface, ear tags, extra limbs, deformed animals, brown cattle, camera
movement (for CCTV shots), cuts, people running, aggressive handling
```

---

## 6. Pasca-produksi dan masuk ke pipeline

1. **Marker ArUco.** Veo tidak bisa menggambar marker ArUco yang valid, sehingga pengukuran berat akan gagal (`marker_not_detected`). Ada dua pilihan:
   - Tempel `06_aruco_marker_id7.png` di atas kartu putih pada frame-frame A3, mengikuti 4 sudut kartu (homography). Saya bisa mengerjakan ini dengan OpenCV setelah videonya jadi.
   - Atau biarkan apa adanya, lalu tunjukkan bahwa sistem meminta review dan berat diambil dari fixture. Ini juga jujur dan sesuai PRD.
2. **Identitas moncong.** Tekstur moncong buatan AI tidak cocok dengan sapi mana pun di galeri, jadi hasil enrollment-nya `new` (sapi baru). Untuk demo pendaftaran ini sesuai harapan. Demo "scan ulang sapi yang sama" tidak bisa memakai video Veo.
3. **Layout:** kanvas 1920×1080, CCTV di kiri (sekitar 1280×720), HP di kanan (sekitar 405×720), timestamp CCTV dan overlay UI aplikasi (kotak panduan moncong, checklist view) ditambahkan di editor.
4. **Masuk ke backend:**
   - Video A → `POST /enrollments` → upload → process → confirm (lihat `services/api/README.md`).
   - Video B → buat kamera dan zona (gambar polygon zona kuning sesuai posisinya di video) → `POST /cameras/{id}/scans` dengan `scanned_at` = mulai rekaman + 4 detik → `POST /cameras/{id}/recordings` → worker. Track yang keluar dari zona akan membawa identitas sapi baru itu, dan evidence clip-nya berasal dari video ini.
