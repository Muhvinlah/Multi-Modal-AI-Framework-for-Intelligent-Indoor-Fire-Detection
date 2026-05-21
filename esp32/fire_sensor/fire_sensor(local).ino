// ==============================================================================
// Tujuan       : Firmware ESP32 untuk 6 sensor gas MQ + DHT22 + kirim data via HTTP
//                Sensor: MQ135, MQ2, MQ3, MQ4, MQ5, MQ7, DHT22
//                Fitur: WiFi Captive Portal untuk konfigurasi awal
// Caller       : Hardware ESP32 (upload via Arduino IDE)
// Dependensi   : WiFi.h, HTTPClient.h, WebServer.h, Preferences.h, ArduinoJson.h, DHT.h
// Main Functions: setup(), loop(), readMQSensor(), readDHTSensor(), sendDataToServer()
//                 startConfigPortal(), handleConfigPage(), handleSaveConfig()
// Side Effects : HTTP POST ke backend setiap 2 detik
//                NVS storage untuk persist konfigurasi WiFi & server
// ==============================================================================
// RESET KONFIGURASI:
//   Tahan tombol BOOT (GPIO0) selama 5 detik saat ESP32 menyala.
//   LED akan berkedip cepat, lalu ESP32 restart ke mode AP konfigurasi.
// ==============================================================================

#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <WebServer.h>
#include <Preferences.h>
#include <ArduinoJson.h>
#include <DHT.h>

// ===========================
// KONFIGURASI CAPTIVE PORTAL
// ===========================
const char* AP_SSID = "Kel6Api";
const char* AP_PASS = "farhan123";

// ===========================
// PIN DEFINISI
// ===========================
const int mqPins[] = {32, 33, 34, 35, 36, 39};
const int jumlahSensor = 6;
String namaSensor[] = {"MQ-4 (LPG)", "MQ-5 (NATURAL GAS)", "MQ-135 (Air)", "MQ-2 (SMOKE)", "MQ-7 (CO)", "MQ-3 (ALCOHOL)"};
int sensorValues[6] = {0, 0, 0, 0, 0, 0};

#define LED_PIN   2    // LED built-in
#define RESET_PIN 0    // Tombol BOOT (GPIO0) untuk reset konfigurasi

// [TAMBAHAN] Pin & Tipe untuk DHT22
#define DHTPIN 4       // DHT22 Pin Data dihubungkan ke GPIO 4
#define DHTTYPE DHT22  // Menggunakan DHT22 karena sensor berwarna putih
DHT dht(DHTPIN, DHTTYPE);

// ===========================
// VARIABEL GLOBAL
// ===========================
Preferences preferences;
WebServer configServer(80);

String cfg_ssid     = "";
String cfg_password = "";
String cfg_url      = "";
String cfg_camera   = "";

unsigned long lastSendTime = 0;
const unsigned long SEND_INTERVAL = 2000;
bool wifiConnected = false;
bool configMode = false;

// [TAMBAHAN] Variabel untuk menampung suhu dan kelembapan
float currentTemp = 0.0;
float currentHum = 0.0;

// Fungsi Prototipe
void connectWiFi();
int readMQSensor(int pin);
void readDHTSensor();
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
    <meta charset="UTF-8">
    <title>🔥 Sensor Setup</title>
    <style>
        body{font-family:sans-serif;background:#111;color:#eee;padding:20px;}
        input,button{width:100%;padding:10px;margin:5px 0;border-radius:6px;border:none;}
        input{background:#222;color:#fff;} 
        button{background:#e53e3e;color:#fff;font-weight:bold;cursor:pointer;}
    </style>
  </head>
  <body>
    <h2>🔥 Fire Sensor Setup</h2>
    <form action="/save" method="POST">
      <input type="text" name="ssid" placeholder="WiFi SSID" required><br>
      <input type="password" name="pass" placeholder="WiFi Password" required><br>
      <input type="text" name="url" placeholder="Server URL (e.g. http://192.168.x.x/api/sensor)" required><br>
      <input type="text" name="cam" placeholder="Camera ID" required><br>
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
  Serial.println("ESP32 Fire Detection Sensor Module");
  Serial.println("========================================");

  pinMode(LED_PIN, OUTPUT);
  pinMode(RESET_PIN, INPUT_PULLUP);
  digitalWrite(LED_PIN, LOW);

  // Cek tombol RESET saat boot
  checkResetButton();

  // Coba load konfigurasi dari NVS
  if (!loadConfig()) {
    // Belum dikonfigurasi → masuk AP mode
    Serial.println("[Config] Belum ada konfigurasi. Masuk mode setup...");
    startConfigPortal();
    return; // Loop akan handle config mode
  }

  // Konfigurasi ditemukan → mode normal
  Serial.printf("[Config] SSID: %s\n", cfg_ssid.c_str());
  Serial.printf("[Config] URL:  %s\n", cfg_url.c_str());
  Serial.printf("[Config] Cam:  %s\n", cfg_camera.c_str());

  connectWiFi();
  analogReadResolution(12);

  // [TAMBAHAN] Inisialisasi Sensor DHT22
  dht.begin();
  Serial.println("[Sensor] DHT22 Initialized!");

  // Pemanasan sensor
  Serial.println("[Sensor] Warming up (20 detik)...");
  for (int i = 20; i > 0; i--) {
    Serial.printf("  %d detik tersisa...\n", i);
    digitalWrite(LED_PIN, !digitalRead(LED_PIN));
    delay(1000);
  }
  digitalWrite(LED_PIN, HIGH);
  Serial.println("[Sensor] Sensor siap!");
}

// ===========================
// LOOP UTAMA
// ===========================
void loop() {
  // Jika dalam mode konfigurasi, handle web server
  if (configMode) {
    configServer.handleClient();
    // LED blink lambat saat AP mode
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
        // Blink cepat sebagai indikator
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
    
    // [TAMBAHAN] Baca data DHT22 sebelum membaca MQ
    readDHTSensor();
    Serial.printf("Suhu: %.1f C | Kelembapan: %.1f %%\n", currentTemp, currentHum);

    for (int i = 0; i < jumlahSensor; i++) {
      sensorValues[i] = readMQSensor(mqPins[i]);
      Serial.printf("%s: %d | ", namaSensor[i].c_str(), sensorValues[i]);
    }
    Serial.println();

    if (wifiConnected) {
      sendDataToServer();
    }

    digitalWrite(LED_PIN, LOW);
    delay(50);
    digitalWrite(LED_PIN, HIGH);
  }
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
// FUNGSI: Baca Sensor MQ
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
// FUNGSI: Kirim Data ke Server
// ===========================
void sendDataToServer() {
  JsonDocument doc;
  HTTPClient http;
  http.begin(cfg_url.c_str());
  http.addHeader("Content-Type", "application/json");

  doc["camera_id"] = cfg_camera;
  doc["mq4"]   = sensorValues[0];
  doc["mq5"]   = sensorValues[1];
  doc["mq135"] = sensorValues[2];
  doc["mq2"]   = sensorValues[3];
  doc["mq7"]   = sensorValues[4];
  doc["mq3"]   = sensorValues[5];
  
  // [TAMBAHAN] Masukkan data suhu dan kelembapan ke dalam Payload
  doc["temperature"] = currentTemp;
  doc["humidity"]    = currentHum;

  String jsonPayload;
  serializeJson(doc, jsonPayload);

  int httpCode = http.POST(jsonPayload);

  if (httpCode > 0) {
    if (httpCode == 200) {
      String response = http.getString();
      Serial.printf("[HTTP] Server: %s\n", response.c_str());
    } else {
      Serial.printf("[HTTP] POST failed (code): %d\n", httpCode);
    }
  } else {
    Serial.printf("[HTTP] POST gagal: %s\n", http.errorToString(httpCode).c_str());
  }

  http.end();
}

// ===========================
// FUNGSI: Koneksi WiFi (STA)
// ===========================
void connectWiFi() {
  Serial.printf("[WiFi] Connecting to %s", cfg_ssid.c_str());
  WiFi.mode(WIFI_STA);
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
  preferences.begin("firesensor", true); // read-only
  cfg_ssid     = preferences.getString("ssid", "");
  cfg_password = preferences.getString("pass", "");
  cfg_url      = preferences.getString("url",  "");
  cfg_camera   = preferences.getString("cam",  "");
  preferences.end();

  // Konfigurasi valid jika minimal SSID dan URL ada
  return (cfg_ssid.length() > 0 && cfg_url.length() > 0);
}

// ===========================
// FUNGSI: Simpan Konfigurasi ke NVS
// ===========================
void saveConfig() {
  preferences.begin("firesensor", false); // read-write
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
      // Blink konfirmasi
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
  configServer.send(200, "text/html", CONFIG_PAGE); // Pastikan CONFIG_PAGE dideklarasikan di file utama kamu
}

// ===========================
// FUNGSI: Simpan dari Form & Restart
// ===========================
void handleSaveConfig() {
  cfg_ssid     = configServer.arg("ssid");
  cfg_password = configServer.arg("pass");
  cfg_url      = configServer.arg("url");
  cfg_camera   = configServer.arg("cam");

  if (cfg_ssid.length() == 0 || cfg_url.length() == 0) {
    configServer.send(400, "text/plain", "SSID dan URL wajib diisi!");
    return;
  }

  saveConfig();
  configServer.send(200, "text/html", SAVE_PAGE); // Pastikan SAVE_PAGE dideklarasikan di file utama kamu

  Serial.println("[Config] Restart dalam 3 detik...");
  delay(3000);
  ESP.restart();
}