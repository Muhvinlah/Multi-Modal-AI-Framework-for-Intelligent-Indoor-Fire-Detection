// ==============================================================================
// Tujuan       : Firmware ESP32 untuk 6 sensor gas MQ + DHT22 + IR Flame Sensor
//                + kirim data via HTTPS (Cloudflare Tunnel compatible)
//                Sensor: MQ135, MQ2, MQ3, MQ4, MQ5, MQ7, DHT22, IR Flame
//                Fitur: WiFi Captive Portal + HTTPS
// Caller       : Hardware ESP32 (upload via Arduino IDE)
// Dependensi   : WiFi.h, HTTPClient.h, WebServer.h, Preferences.h, ArduinoJson.h,
//                DHT.h, WiFiClientSecure.h
// Main Functions: setup(), loop(), readMQSensor(), readDHTSensor(),
//                 readFlameSensor(), sendDataToServer(),
//                 startConfigPortal(), handleConfigPage(), handleSaveConfig()
// Side Effects : HTTPS POST ke backend setiap 2 detik
//                NVS storage untuk persist konfigurasi WiFi & server
// ==============================================================================
// PIN MAPPING:
//   GPIO 32, 33, 34, 35, 36, 39  →  6 sensor MQ (ADC1, WiFi-safe)
//   GPIO 4                        →  DHT22 data
//   GPIO 27                       →  IR Flame Sensor digital output (D0)
//   GPIO 2                        →  LED built-in
//   GPIO 0                        →  BOOT button / Reset config
// ==============================================================================
// PRODUCTION DEPLOYMENT:
//   Endpoint default: https://api.firedetection.my.id/api/sensor
//   TLS Mode: setInsecure() — skip cert verify (OK untuk PBL/demo)
// ==============================================================================
// RESET KONFIGURASI:
//   Tahan tombol BOOT (GPIO0) selama 5 detik saat ESP32 menyala.
// ==============================================================================
// IR FLAME SENSOR NOTES:
//   - Modul umum (KY-026, FC-04): output D0 = LOW saat api terdeteksi (active LOW)
//   - Jika modul lo active HIGH, ubah #define IR_FLAME_ACTIVE_LOW jadi false
//   - Sensitivity diatur via potensiometer di modul (putar pelan-pelan
//     pakai obeng kecil sambil cek serial monitor)
//   - Range deteksi: 760nm-1100nm IR (flame emits this), ~80cm jarak
// ==============================================================================

#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <DHT.h>

// ===========================
// KONFIGURASI CAPTIVE PORTAL
// ===========================
const char* AP_SSID = "Kel6Api";
const char* AP_PASS = "farhan123";

const char* DEFAULT_SERVER_URL = "https://api.firedetection.my.id/api/sensor";

// ===========================
// PIN DEFINISI
// ===========================
const int mqPins[] = {32, 33, 34, 35, 36, 39};
const int jumlahSensor = 6;
String namaSensor[] = {"MQ-4 (LPG)", "MQ-5 (NATURAL GAS)", "MQ-135 (Air)", "MQ-2 (SMOKE)", "MQ-7 (CO)", "MQ-3 (ALCOHOL)"};
int sensorValues[6] = {0, 0, 0, 0, 0, 0};

#define LED_PIN   2    // LED built-in
#define RESET_PIN 0    // Tombol BOOT (GPIO0) untuk reset konfigurasi

// Pin & Tipe untuk DHT22
#define DHTPIN 26
#define DHTTYPE DHT22
DHT dht(DHTPIN, DHTTYPE);

// [BARU] Pin IR Flame Sensor
#define IR_FLAME_PIN         27       // Digital output (D0) dari modul IR flame
#define IR_FLAME_ACTIVE_LOW  true     // true = LOW saat api terdeteksi (KY-026, FC-04)
                                       // false = HIGH saat api terdeteksi (rare)

// ===========================
// VARIABEL GLOBAL
// ===========================
Preferences preferences;
WebServer configServer(80);

WiFiClientSecure secureClient;
WiFiClient plainClient;

String cfg_ssid     = "";
String cfg_password = "";
String cfg_url      = "";
String cfg_camera   = "";

unsigned long lastSendTime = 0;
const unsigned long SEND_INTERVAL = 2000;
bool wifiConnected = false;
bool configMode = false;
bool useHTTPS = false;

unsigned long totalSent = 0;
unsigned long totalFailed = 0;

// DHT22
float currentTemp = 0.0;
float currentHum = 0.0;

// [BARU] IR Flame Sensor
bool flameDetected = false;
unsigned long lastFlameAlertTime = 0;
const unsigned long FLAME_ALERT_THROTTLE = 5000;   // log "FLAME!" max 1x per 5 detik

// Fungsi Prototipe
void connectWiFi();
void setupTLS();
int  readMQSensor(int pin);
void readDHTSensor();
bool readFlameSensor();
void sendDataToServer();
bool loadConfig();
void saveConfig();
void clearConfig();
void startConfigPortal();
void handleConfigPage();
void handleSaveConfig();
void checkResetButton();

// ===========================
// HALAMAN HTML KONFIGURASI
// ===========================
const char CONFIG_PAGE[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Fire Sensor Setup</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: Arial, sans-serif; background: #1a1a2e; color: #e0e0e0;
           display: flex; justify-content: center; align-items: center;
           min-height: 100vh; padding: 20px; }
    .card { background: #16213e; border-radius: 16px; padding: 32px;
            max-width: 420px; width: 100%; box-shadow: 0 8px 32px rgba(0,0,0,0.4); }
    h1 { text-align: center; color: #e94560; margin-bottom: 8px; font-size: 22px; }
    p.sub { text-align: center; color: #888; margin-bottom: 24px; font-size: 13px; }
    label { display: block; font-size: 13px; color: #aaa; margin-bottom: 4px; margin-top: 16px; }
    input[type=text], input[type=password], input[type=url] {
      width: 100%; padding: 12px; border: 1px solid #333; border-radius: 8px;
      background: #0f3460; color: #fff; font-size: 15px; outline: none; }
    input:focus { border-color: #e94560; }
    button { width: 100%; padding: 14px; margin-top: 24px; border: none;
             border-radius: 8px; background: #e94560; color: #fff;
             font-size: 16px; font-weight: bold; cursor: pointer; }
    button:hover { background: #c73e54; }
    .info { text-align: center; color: #666; font-size: 11px; margin-top: 16px; }
    .hint { color: #4ecca3; font-size: 11px; margin-top: 4px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>&#128293; Fire Sensor Setup</h1>
    <p class="sub">Konfigurasi WiFi & Server</p>
    <form action="/save" method="POST">
      <label>WiFi SSID</label>
      <input type="text" name="ssid" placeholder="Nama WiFi" required>
      <label>WiFi Password</label>
      <input type="password" name="pass" placeholder="Password WiFi">
      <label>Server URL</label>
      <input type="url" name="url" placeholder="https://api.firedetection.my.id/api/sensor"
             value="https://api.firedetection.my.id/api/sensor" required>
      <p class="hint">Default: production endpoint via Cloudflare Tunnel</p>
      <label>Camera ID</label>
      <input type="text" name="cam" placeholder="cam_01" value="cam_01" required>
      <button type="submit">Simpan & Restart</button>
    </form>
    <p style="margin-top:20px;font-size:12px;color:#888;">💡 Tahan tombol BOOT 5 detik untuk reset konfigurasi.</p>
  </body>
</html>
)rawliteral";

const char SAVE_PAGE[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
  <head>
    <meta charset="UTF-8">
    <title>✅ Saved</title>
    <style>
      body{font-family:sans-serif;background:#111;color:#eee;text-align:center;padding:40px;}
      h2{color:#48bb78;} 
      .spin{
        border:4px solid #333;
        border-top:4px solid #48bb78;
        border-radius:50%;
        width:30px;
        height:30px;
        animation:spin 1s linear infinite;
        margin:20px auto;
      }
      @keyframes spin{
        0%{transform:rotate(0deg);}
        100%{transform:rotate(360deg);}}
    </style>
  </head>
  <body>
    <h2>✅ Konfigurasi Tersimpan!</h2>
    <div class="spin"></div>
    <p>ESP32 akan restart dalam 3 detik...</p>
  </body>
</html>
)rawliteral";

// ===========================
// SETUP
// ===========================
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("========================================");
  Serial.println("ESP32 Fire Detection Sensor Module v2.1");
  Serial.println("Build: HTTPS + IR Flame Sensor");
  Serial.printf("Free heap awal: %d bytes\n", ESP.getFreeHeap());
  Serial.println("========================================");

  pinMode(LED_PIN, OUTPUT);
  pinMode(RESET_PIN, INPUT_PULLUP);
  digitalWrite(LED_PIN, LOW);

  // [BARU] Inisialisasi pin IR Flame Sensor
  // INPUT_PULLUP — kalau modul disconnect, default ke HIGH (no false alarm di active LOW)
  pinMode(IR_FLAME_PIN, INPUT_PULLUP);

  // Cek tombol RESET saat boot
  checkResetButton();

  // Coba load konfigurasi dari NVS
  if (!loadConfig()) {
    Serial.println("[Config] Belum ada konfigurasi. Masuk mode setup...");
    startConfigPortal();
    return;
  }

  useHTTPS = cfg_url.startsWith("https://");

  Serial.printf("[Config] SSID:  %s\n", cfg_ssid.c_str());
  Serial.printf("[Config] URL:   %s\n", cfg_url.c_str());
  Serial.printf("[Config] Cam:   %s\n", cfg_camera.c_str());
  Serial.printf("[Config] Mode:  %s\n", useHTTPS ? "HTTPS (TLS)" : "HTTP (plain)");

  connectWiFi();

  if (useHTTPS) {
    setupTLS();
  }

  analogReadResolution(12);

  // Inisialisasi Sensor DHT22
  dht.begin();
  Serial.println("[Sensor] DHT22 Initialized!");

  // [BARU] Cek initial state IR flame sensor
  Serial.printf("[Sensor] IR Flame initial state: %s (raw=%d)\n",
                readFlameSensor() ? "DETECTED ⚠️" : "OK (no flame)",
                digitalRead(IR_FLAME_PIN));
  Serial.println("[Sensor] Tip: putar potensio di modul IR untuk adjust sensitivity");

  // Pemanasan sensor MQ (IR sensor gak butuh warmup)
  Serial.println("[Sensor] Warming up MQ sensors (20 detik)...");
  for (int i = 20; i > 0; i--) {
    Serial.printf("  %d detik tersisa...\n", i);
    digitalWrite(LED_PIN, !digitalRead(LED_PIN));
    delay(1000);
  }
  digitalWrite(LED_PIN, HIGH);
  Serial.println("[Sensor] Semua sensor siap!");
  Serial.printf("[Sensor] Free heap setelah setup: %d bytes\n", ESP.getFreeHeap());
}

// ===========================
// LOOP UTAMA
// ===========================
void loop() {
  // Jika dalam mode konfigurasi, handle web server
  if (configMode) {
    configServer.handleClient();
    static unsigned long lastBlink = 0;
    if (millis() - lastBlink > 500) {
      lastBlink = millis();
      digitalWrite(LED_PIN, !digitalRead(LED_PIN));
    }
    return;
  }

  // Cek tombol reset saat runtime
  if (digitalRead(RESET_PIN) == LOW) {
    unsigned long pressStart = millis();
    while (digitalRead(RESET_PIN) == LOW) {
      delay(100);
      if (millis() - pressStart >= 5000) {
        Serial.println("[Config] RESET! Menghapus konfigurasi...");
        for (int i = 0; i < 20; i++) {
          digitalWrite(LED_PIN, !digitalRead(LED_PIN));
          delay(100);
        }
        clearConfig();
        ESP.restart();
      }
    }
  }

  // Reconnect WiFi jika terputus
  if (WiFi.status() != WL_CONNECTED) {
    wifiConnected = false;
    connectWiFi();
  }

  unsigned long now = millis();
  if (now - lastSendTime >= SEND_INTERVAL) {
    lastSendTime = now;

    Serial.println("--- Sensor Reading ---");

    // Baca DHT22
    readDHTSensor();
    Serial.printf("Suhu: %.1f C | Kelembapan: %.1f %%\n", currentTemp, currentHum);

    // [BARU] Baca IR Flame Sensor (sebelum MQ biar prioritas tinggi)
    flameDetected = readFlameSensor();
    if (flameDetected) {
      // Throttle alert log biar gak spam
      if (millis() - lastFlameAlertTime > FLAME_ALERT_THROTTLE) {
        Serial.println("🔥🔥🔥 [FLAME] API TERDETEKSI! 🔥🔥🔥");
        lastFlameAlertTime = millis();
      }
      // Visual indicator: LED kedip cepat saat flame detected
      for (int i = 0; i < 6; i++) {
        digitalWrite(LED_PIN, !digitalRead(LED_PIN));
        delay(50);
      }
      digitalWrite(LED_PIN, HIGH);
    }

    // Baca semua MQ
    for (int i = 0; i < jumlahSensor; i++) {
      sensorValues[i] = readMQSensor(mqPins[i]);
      Serial.printf("%s: %d | ", namaSensor[i].c_str(), sensorValues[i]);
    }
    Serial.printf("FLAME: %s\n", flameDetected ? "YES" : "no");

    if (wifiConnected) {
      sendDataToServer();
    } else {
      Serial.println("[Send] Skip — WiFi belum connect");
    }

    // Heap monitoring (debug TLS leak)
    if (totalSent % 30 == 0 && totalSent > 0) {
      Serial.printf("[Stats] Sent: %lu | Failed: %lu | Free heap: %d\n",
                    totalSent, totalFailed, ESP.getFreeHeap());
    }

    // Heartbeat LED (kalau gak ada flame)
    if (!flameDetected) {
      digitalWrite(LED_PIN, LOW);
      delay(50);
      digitalWrite(LED_PIN, HIGH);
    }
  }
}

// ===========================
// FUNGSI: Setup TLS Client
// ===========================
void setupTLS() {
  secureClient.setInsecure();
  secureClient.setTimeout(15);
  Serial.println("[TLS] Secure client initialized (insecure mode)");
}

// ===========================
// FUNGSI: Baca Sensor DHT22
// ===========================
void readDHTSensor() {
  float h = dht.readHumidity();
  float t = dht.readTemperature();

  if (isnan(h) || isnan(t)) {
    Serial.println("[Sensor Error] Gagal membaca data dari DHT22!");
  } else {
    currentTemp = t;
    currentHum = h;
  }
}

// ===========================
// FUNGSI: Baca Sensor MQ (analog, 10x oversampling)
// ===========================
int readMQSensor(int pin) {
  long total = 0;
  for (int i = 0; i < 10; i++) {
    total += analogRead(pin);
    delay(2);
  }
  return total / 10;
}

// ===========================
// [BARU] FUNGSI: Baca IR Flame Sensor (digital, majority vote)
// ===========================
// Ambil 5 sample dengan jeda 5ms, return true kalau >= 3 sample positif.
// Mengurangi false positive akibat noise EMI dari WiFi/relay.
bool readFlameSensor() {
  int activeCount = 0;
  int targetLevel = IR_FLAME_ACTIVE_LOW ? LOW : HIGH;

  for (int i = 0; i < 5; i++) {
    if (digitalRead(IR_FLAME_PIN) == targetLevel) {
      activeCount++;
    }
    delay(5);
  }

  return (activeCount >= 3);   // Majority vote (3/5)
}

// ===========================
// FUNGSI: Kirim Data ke Server (HTTPS-aware)
// ===========================
void sendDataToServer() {
  JsonDocument doc;
  HTTPClient http;

  bool beginOk;
  if (useHTTPS) {
    beginOk = http.begin(secureClient, cfg_url);
  } else {
    beginOk = http.begin(plainClient, cfg_url);
  }

  if (!beginOk) {
    Serial.println("[HTTP] begin() gagal — cek URL");
    totalFailed++;
    return;
  }

  http.addHeader("Content-Type", "application/json");
  http.addHeader("User-Agent", "ESP32-FireDetect/2.1");
  http.addHeader("Connection", "keep-alive");
  http.setTimeout(10000);
  http.setConnectTimeout(5000);
  http.setReuse(true);

  // Build JSON payload — 384 byte cukup untuk 9 field
  StaticJsonDocument<384> doc;
  doc["camera_id"]      = cfg_camera;
  doc["mq4"]            = sensorValues[0];
  doc["mq5"]            = sensorValues[1];
  doc["mq135"]          = sensorValues[2];
  doc["mq2"]            = sensorValues[3];
  doc["mq7"]            = sensorValues[4];
  doc["mq3"]            = sensorValues[5];
  doc["temperature"]    = currentTemp;
  doc["humidity"]       = currentHum;
  doc["flame_detected"] = flameDetected;     // [BARU] IR flame sensor

  String jsonPayload;
  serializeJson(doc, jsonPayload);

  int httpCode = http.POST(jsonPayload);

  if (httpCode > 0) {
    if (httpCode == 200) {
      totalSent++;
    } else if (httpCode == 401 || httpCode == 403) {
      Serial.printf("[HTTP] Auth failed: %d — cek endpoint terbuka untuk ESP32\n", httpCode);
      totalFailed++;
    } else if (httpCode == 429) {
      Serial.println("[HTTP] Rate limited (429) — slow down");
      totalFailed++;
    } else if (httpCode == 502 || httpCode == 503) {
      Serial.printf("[HTTP] Server down (%d) — FastAPI mungkin restart\n", httpCode);
      totalFailed++;
    } else {
      Serial.printf("[HTTP] Unexpected status: %d\n", httpCode);
      totalFailed++;
    }
  } else {
    const char* errStr = http.errorToString(httpCode).c_str();
    Serial.printf("[HTTP] POST gagal (%d): %s\n", httpCode, errStr);
    totalFailed++;

    if (httpCode == HTTPC_ERROR_CONNECTION_REFUSED ||
        httpCode == HTTPC_ERROR_CONNECTION_LOST) {
      Serial.printf("[HTTP] Free heap saat error: %d\n", ESP.getFreeHeap());
    }
  }

  http.end();
}

// ===========================
// FUNGSI: Koneksi WiFi (STA)
// ===========================
void connectWiFi() {
  Serial.printf("[WiFi] Connecting to %s", cfg_ssid.c_str());

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);   // Stabilitas TLS
  WiFi.begin(cfg_ssid.c_str(), cfg_password.c_str());

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    wifiConnected = true;
    Serial.println();
    Serial.printf("[WiFi] Connected! IP: %s\n", WiFi.localIP().toString().c_str());
    Serial.printf("[WiFi] Signal: %d dBm\n", WiFi.RSSI());
  } else {
    wifiConnected = false;
    Serial.println();
    Serial.println("[WiFi] Connection failed! Retrying in 5s...");
    delay(5000);
  }
}

// ===========================
// FUNGSI: Load Konfigurasi dari NVS
// ===========================
bool loadConfig() {
  preferences.begin("firesensor", true);
  cfg_ssid     = preferences.getString("ssid", "");
  cfg_password = preferences.getString("pass", "");
  cfg_url      = preferences.getString("url",  "");
  cfg_camera   = preferences.getString("cam",  "");
  preferences.end();

  return (cfg_ssid.length() > 0 && cfg_url.length() > 0);
}

// ===========================
// FUNGSI: Simpan Konfigurasi ke NVS
// ===========================
void saveConfig() {
  preferences.begin("firesensor", false);
  preferences.putString("ssid", cfg_ssid);
  preferences.putString("pass", cfg_password);
  preferences.putString("url",  cfg_url);
  preferences.putString("cam",  cfg_camera);
  preferences.end();
  Serial.println("[Config] Konfigurasi tersimpan ke NVS!");
}

// ===========================
// FUNGSI: Hapus Konfigurasi (Reset)
// ===========================
void clearConfig() {
  preferences.begin("firesensor", false);
  preferences.clear();
  preferences.end();
  Serial.println("[Config] Konfigurasi dihapus!");
}

// ===========================
// FUNGSI: Cek Tombol Reset Saat Boot
// ===========================
void checkResetButton() {
  if (digitalRead(RESET_PIN) == LOW) {
    Serial.println("[Config] Tombol BOOT terdeteksi saat boot...");
    unsigned long start = millis();
    while (digitalRead(RESET_PIN) == LOW && (millis() - start) < 5000) {
      digitalWrite(LED_PIN, !digitalRead(LED_PIN));
      delay(200);
    }
    if (millis() - start >= 5000) {
      Serial.println("[Config] RESET KONFIGURASI!");
      clearConfig();
      for (int i = 0; i < 10; i++) {
        digitalWrite(LED_PIN, !digitalRead(LED_PIN));
        delay(100);
      }
    }
  }
}

// ===========================
// FUNGSI: Mulai Captive Portal AP
// ===========================
void startConfigPortal() {
  configMode = true;

  WiFi.mode(WIFI_AP);
  WiFi.softAP(AP_SSID, AP_PASS);
  delay(100);

  Serial.println("========================================");
  Serial.println("[AP] Mode Konfigurasi Aktif!");
  Serial.printf("[AP] SSID: %s\n", AP_SSID);
  Serial.printf("[AP] Pass: %s\n", AP_PASS);
  Serial.printf("[AP] IP:   %s\n", WiFi.softAPIP().toString().c_str());
  Serial.println("[AP] Buka browser → http://192.168.4.1");
  Serial.println("========================================");

  configServer.on("/", handleConfigPage);
  configServer.on("/save", HTTP_POST, handleSaveConfig);
  configServer.begin();
}

// ===========================
// FUNGSI: Tampilkan Halaman Konfigurasi
// ===========================
void handleConfigPage() {
  configServer.send(200, "text/html", CONFIG_PAGE);
}

// ===========================
// FUNGSI: Simpan dari Form & Restart
// ===========================
void handleSaveConfig() {
  cfg_ssid     = configServer.arg("ssid");
  cfg_password = configServer.arg("pass");
  cfg_url      = configServer.arg("url");
  cfg_camera   = configServer.arg("cam");

  cfg_ssid.trim();
  cfg_url.trim();
  cfg_camera.trim();

  if (cfg_ssid.length() == 0 || cfg_url.length() == 0) {
    configServer.send(400, "text/plain", "SSID dan URL wajib diisi!");
    return;
  }

  if (!cfg_url.startsWith("http://") && !cfg_url.startsWith("https://")) {
    configServer.send(400, "text/plain",
                      "URL harus mulai dengan http:// atau https://");
    return;
  }

  if (cfg_url.startsWith("http://")) {
    Serial.println("[Config] ⚠️ HTTP (plain) — gak aman, gunakan HTTPS untuk production");
  }

  saveConfig();
  configServer.send(200, "text/html", SAVE_PAGE);

  Serial.println("[Config] Restart dalam 3 detik...");
  delay(3000);
  ESP.restart();
}
