// ==============================================================================
// ESP32 Firmware Patch — HTTPS Support untuk firedetection.my.id
// ==============================================================================
// Apply patch ini ke esp32/fire_sensor/fire_sensor.ino
//
// Yang berubah:
// 1. WiFiClient → WiFiClientSecure (TLS support)
// 2. http://ip:8000/api/sensor → https://api.firedetection.my.id/api/sensor
// 3. setInsecure() untuk skip cert verify (OK untuk PBL, simpler)
// 4. Timeout dinaikkan (CF Tunnel kadang cold-start ~2-5 detik)
// 5. User-Agent custom untuk traceability
//
// CATATAN:
// - Endpoint server di-stored di NVS via captive portal — pastikan
//   captive portal lo allow URL input (bukan IP-only), atau hardcode dulu
// - Untuk production beneran, embed CA cert ISRG Root X1 pakai setCACert()
// ==============================================================================

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <Preferences.h>

// ==============================================================================
// HARDCODED ENDPOINT — kalau captive portal belum support URL config
// ==============================================================================
#define DEFAULT_SERVER_URL "https://api.firedetection.my.id/api/sensor"

Preferences prefs;
WiFiClientSecure secureClient;

// Buffer untuk URL dari NVS (max 128 char)
char serverUrl[128];


// ==============================================================================
// Setup TLS Client (call sekali saat boot, setelah WiFi connected)
// ==============================================================================
void setupSecureClient() {
  // OPSI 1: Skip TLS verify (simpler, OK untuk PBL/demo)
  secureClient.setInsecure();

  // OPSI 2 (production): Embed Cloudflare root CA
  // Uncomment dan paste cert ISRG Root X1 di sini kalau mau strict verify
  // secureClient.setCACert(rootCACertificate);

  Serial.println("[TLS] Secure client initialized (insecure mode)");
}


// ==============================================================================
// Load server URL dari NVS (kalau ada), fallback ke default
// ==============================================================================
void loadServerUrl() {
  prefs.begin("config", true);   // read-only
  String savedUrl = prefs.getString("server_url", "");
  prefs.end();

  if (savedUrl.length() > 0 && savedUrl.startsWith("https://")) {
    strncpy(serverUrl, savedUrl.c_str(), sizeof(serverUrl) - 1);
    Serial.print("[Config] Loaded URL from NVS: ");
    Serial.println(serverUrl);
  } else {
    strncpy(serverUrl, DEFAULT_SERVER_URL, sizeof(serverUrl) - 1);
    Serial.print("[Config] Using default URL: ");
    Serial.println(serverUrl);
  }
}


// ==============================================================================
// Kirim data sensor ke server (panggil tiap 2 detik dari loop())
// ==============================================================================
bool sendSensorData(
  const String& cameraId,
  float mq2, float mq3, float mq4, float mq5, float mq7, float mq135,
  float temperature, float humidity
) {
  // Cek WiFi dulu
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[HTTP] WiFi disconnected, attempting reconnect...");
    WiFi.reconnect();
    return false;
  }

  HTTPClient https;
  https.setTimeout(10000);              // 10 detik (CF Tunnel cold-start tolerance)
  https.setReuse(true);                  // Keep-alive
  https.setConnectTimeout(5000);

  if (!https.begin(secureClient, serverUrl)) {
    Serial.println("[HTTPS] begin() failed");
    return false;
  }

  https.addHeader("Content-Type", "application/json");
  https.addHeader("User-Agent", "ESP32-FireDetect/1.0");
  https.addHeader("Connection", "keep-alive");

  // Build JSON payload sesuai SensorPayload pydantic di app/sensor.py
  String payload = "{";
  payload += "\"camera_id\":\"" + cameraId + "\",";
  payload += "\"mq2\":" + String(mq2, 2) + ",";
  payload += "\"mq3\":" + String(mq3, 2) + ",";
  payload += "\"mq4\":" + String(mq4, 2) + ",";
  payload += "\"mq5\":" + String(mq5, 2) + ",";
  payload += "\"mq7\":" + String(mq7, 2) + ",";
  payload += "\"mq135\":" + String(mq135, 2) + ",";
  payload += "\"temperature\":" + String(temperature, 2) + ",";
  payload += "\"humidity\":" + String(humidity, 2);
  payload += "}";

  int httpCode = https.POST(payload);
  bool success = false;

  if (httpCode > 0) {
    if (httpCode == 200) {
      success = true;
      // Optional: parse response body untuk update threshold dinamis
      // String resp = https.getString();
    } else {
      Serial.printf("[HTTPS] Unexpected status: %d\n", httpCode);
    }
  } else {
    Serial.printf("[HTTPS] POST failed: %s\n", https.errorToString(httpCode).c_str());
  }

  https.end();
  return success;
}


// ==============================================================================
// Captive Portal — tambah field input URL server
// ==============================================================================
// Di handler captive portal HTML, tambah:
//
//   <label>Server URL (https://):</label>
//   <input type="url" name="server_url" placeholder="https://api.firedetection.my.id/api/sensor" required>
//
// Di handler POST captive portal, simpan ke NVS:
//
//   String urlInput = server.arg("server_url");
//   if (urlInput.startsWith("https://")) {
//     prefs.begin("config", false);
//     prefs.putString("server_url", urlInput);
//     prefs.end();
//   }
//
// Setelah save, ESP.restart() biar load config baru.
