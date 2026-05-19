# FAQ Sistem Deteksi Kebakaran IoT

## Q: Apa itu LSTM anomaly score?
LSTM anomaly score adalah nilai 0.0 sampai 1.0 hasil normalize dari reconstruction error autoencoder, menunjukkan seberapa berbeda pattern sensor saat ini dibanding kondisi normal yang dipelajari model. Score >= 0.5 dianggap anomaly. Score mendekati 1 berarti pattern sangat menyimpang (kemungkinan sensor rusak atau ada kejadian abnormal seperti kebakaran).

## Q: Kenapa LSTM bisa false positive?
LSTM autoencoder dilatih dari data normal. Kalau ada kondisi yang belum pernah dilihat (sensor baru dikalibrasi, ruangan dengan AC, atau bahkan sensor disconnect = nilai 0), bisa kebaca sebagai anomaly. Cara verifikasi: cek nilai sensor manual, kalau wajar berarti false positive.

## Q: Apa fungsi sensor MQ-2?
MQ-2 mendeteksi gas mudah terbakar seperti LPG, propana, metana, alkohol, hidrogen, dan asap. Range deteksi 200-10000 ppm. Di sistem ini dipakai sebagai indikator awal kebakaran karena sensitif ke asap.

## Q: Apa fungsi sensor MQ-3?
MQ-3 mendeteksi uap alkohol dan etanol. Range deteksi 0.05-10 mg/L. Di sistem ini membantu identifikasi cairan mudah terbakar berbasis alkohol.

## Q: Apa fungsi sensor MQ-4?
MQ-4 mendeteksi gas metana (CH4) dan gas alam (natural gas). Range deteksi 300-10000 ppm. Berguna untuk deteksi kebocoran gas alam yang mudah terbakar.

## Q: Apa fungsi sensor MQ-5?
MQ-5 mendeteksi LPG dan gas alam. Range deteksi 200-10000 ppm. Cocok untuk monitoring kebocoran tabung gas LPG di dapur atau ruang utilitas.

## Q: Apa fungsi sensor MQ-7?
MQ-7 mendeteksi karbon monoksida (CO). Range 20-2000 ppm. CO adalah gas berbahaya hasil pembakaran tidak sempurna. Konsentrasi >= 100 ppm sudah berbahaya untuk manusia. Sensor ini critical untuk early warning.

## Q: Apa fungsi sensor MQ-135?
MQ-135 mendeteksi kualitas udara umum: CO2, amonia (NH3), NOx, benzena, dan asap. Dipakai sebagai indikator kualitas udara dan pendukung deteksi asap kebakaran.

## Q: Kenapa ada 6 sensor MQ berbeda?
Setiap MQ punya target gas berbeda untuk coverage lebih luas:
- MQ-2: gas mudah terbakar umum + asap
- MQ-3: alkohol
- MQ-4: metana (CH4)
- MQ-5: LPG + gas alam
- MQ-7: karbon monoksida
- MQ-135: kualitas udara umum (CO2, NH3, NOx, asap)

## Q: Bagaimana cara menggunakan APAR?
Gunakan teknik PASS: Pull (tarik pin pengaman), Aim (arahkan nozzle ke pangkal/dasar api), Squeeze (tekan tuas), Sweep (sapukan dari sisi ke sisi). Jaga jarak aman 1.5-2 meter dari api, dan posisikan diri membelakangi jalur keluar.

## Q: Bagaimana prosedur evakuasi kebakaran?
1. Tetap tenang, jangan panik. 2. Matikan peralatan listrik bila memungkinkan. 3. Keluar melalui jalur evakuasi dan gunakan tangga darurat, JANGAN gunakan lift. 4. Berkumpul di Assembly Point. 5. Laporkan kehadiran ke Floor Warden, jangan kembali ke dalam gedung sebelum dinyatakan aman.

## Q: Bagaimana P3K untuk luka bakar?
Aliri area luka bakar dengan air mengalir suhu ruang selama 15-20 menit. Tutup dengan kasa steril atau kain bersih. Jangan oleskan odol, mentega, atau es langsung ke luka. Jangan pecahkan lepuhan. Segera cari pertolongan medis untuk luka bakar luas.

## Q: Bagaimana P3K korban terpapar asap?
Pindahkan korban ke udara segar, longgarkan pakaian yang ketat, posisikan duduk agar pernapasan lebih lega. Jika korban tidak bernapas, lakukan CPR. Hubungi layanan darurat 118 atau 112 secepatnya.

## Q: Bagaimana cara melakukan CPR dasar?
Pastikan area aman, cek respons dan napas korban. Lakukan kompresi dada di tengah dada, kedalaman sekitar 5 cm, kecepatan 100-120 kompresi per menit. Rasio 30 kompresi : 2 napas bantuan. Lanjutkan sampai bantuan medis datang atau korban merespons.

## Q: Apa saja kelas kebakaran?
- Kelas A: bahan padat (kayu, kertas, kain) — padamkan dengan air, busa, atau powder.
- Kelas B: cairan/gas mudah terbakar (bensin, LPG) — gunakan busa, CO2, atau powder.
- Kelas C: peralatan listrik bertegangan — gunakan CO2 atau powder, JANGAN AIR.
- Kelas D: logam mudah terbakar — gunakan powder khusus kelas D.

## Q: Apa itu kelas kebakaran A?
Kelas A adalah kebakaran bahan padat seperti kayu, kertas, dan kain. Media pemadam yang tepat adalah air, busa, atau dry powder.

## Q: Kebakaran listrik pakai pemadam apa?
Kebakaran listrik termasuk kelas C. Gunakan APAR CO2 atau dry powder. JANGAN gunakan air karena air menghantarkan listrik dan berbahaya bagi penolong.

## Q: Berapa threshold suhu yang dianggap bahaya?
Untuk ruangan biasa (kantor/rumah): >35°C dianggap warning, >45°C dianggap bahaya. Tapi sistem ini pakai decision fusion (YOLO visual + XGBoost sensor), jadi threshold absolut tidak dipakai langsung — yang dipakai adalah probabilitas bahaya fusi.

## Q: Apa perbedaan status Aman, Waspada, Bahaya?
- **Aman**: probabilitas bahaya fusi < 30%, semua sensor dalam range normal.
- **Waspada**: probabilitas 30-70%, ada indikasi awal (asap tipis, gas naik sedikit).
- **Bahaya**: probabilitas >= 70%, perlu evakuasi + notifikasi Telegram otomatis.

## Q: Apa itu YOLOv11 dan XGBoost dalam sistem ini?
YOLOv11 adalah model computer vision yang mendeteksi api dan asap dari stream CCTV. XGBoost adalah model machine learning yang memprediksi bahaya dari data 6 sensor MQ + suhu + kelembapan. Kedua output digabung via decision fusion menjadi satu probabilitas final.

## Q: Apa itu decision fusion?
Decision fusion adalah penggabungan probabilitas dari YOLO (visual) dan XGBoost (sensor) menjadi satu skor bahaya akhir. Bobot YOLO dinaikkan saat confidence visual tinggi, sehingga keputusan lebih robust dibanding hanya mengandalkan satu sumber.

## Q: Apa yang harus dilakukan kalau notifikasi Telegram bilang bahaya?
1. Verifikasi via dashboard — lihat camera feed real-time. 2. Kalau benar ada kebakaran: aktifkan APAR pakai teknik PASS, evakuasi, hubungi 113. 3. Kalau false alarm: cek sensor (mungkin disconnect atau ada gangguan), reset ke status aman via dashboard.

## Q: Bagaimana cara menambah kamera baru?
Buka dashboard → menu "Konfigurasi Kamera" → "Tambah Kamera" → input nama, RTSP URL, dan ID kamera. Setelah disimpan, kamera otomatis masuk ke pipeline analisis tanpa perlu restart server.

## Q: Apa itu Captive Portal di ESP32?
Fitur ESP32 untuk setup WiFi tanpa hardcode credentials. Saat ESP32 pertama menyala atau gagal konek WiFi, ia menjadi access point sendiri. User connect ke AP-nya via HP, browser auto-redirect ke portal konfigurasi, isi SSID/password + URL server + Camera ID, lalu simpan. Credentials tersimpan di NVS (non-volatile storage) sehingga tahan reboot.

## Q: Seberapa sering ESP32 mengirim data sensor?
ESP32 mengirim payload sensor setiap sekitar 2 detik via HTTP POST ke endpoint /api/sensor. Server menerapkan rate limiting minimal 1 detik per IP, dan payload yang semua nilainya 0 diabaikan karena dianggap sensor belum siap.

## Q: Siapa tim developer sistem ini?
Sistem ini dikembangkan oleh tim PBL Semester 6: Ervin, Akmal, Jascon, dan Farhan.

## Q: Apa fungsi chatbot K3 di sistem ini?
Chatbot K3 adalah asisten berbasis SLM lokal (Qwen 2.5 1.5B) dengan RAG yang menjawab pertanyaan keselamatan kerja, membaca kondisi sensor real-time, serta memberi saran berdasarkan status LSTM anomaly dan decision fusion.
