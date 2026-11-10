#include <Arduino.h>
#include <ArduinoJson.h>
#include <WiFi.h>

namespace {
constexpr char kProtocolVersion[] = "1.0";
constexpr uint32_t kHeartbeatMs = 1000;
constexpr uint32_t kCommunicationTimeoutMs = 5000;
constexpr uint32_t kCompressorLockoutMs = 180000;
constexpr float kShedFrequencyHz = 49.85f;
constexpr float kEssentialShedFrequencyHz = 49.40f;
constexpr float kShedRoCoFHzPerS = -0.3f;
constexpr float kRestoreFrequencyHz = 49.95f;
constexpr uint32_t kRestoreSpacingMs = 5000;
constexpr uint8_t kApplianceCount = 8;
constexpr uint8_t kRelayPins[kApplianceCount] = {16, 17, 18, 19, 21, 22, 23, 25};
constexpr bool kEnableLowVoltageOutputs = false;

struct Appliance {
  String id;
  String priority;
  String type;
  bool on = true;
  bool enrolled = true;
  uint32_t lastOffMs = 0;
};

Appliance appliances[kApplianceCount];
uint8_t applianceCount = 0;
uint32_t txSequence = 0;
uint32_t lastRxSequence = 0;
uint32_t lastMessageMs = 0;
uint32_t lastHeartbeatMs = 0;
uint32_t stableSinceMs = 0;
uint32_t lastRestoreMs = 0;
String shedCommands[kApplianceCount];
String restoreCommands[kApplianceCount];
uint8_t shedCommandCount = 0;
uint8_t restoreCommandCount = 0;
float simulatedFrequencyHz = 50.0f;
float simulatedRoCoFHzPerS = 0.0f;
bool haveSequence = false;
String buildingId;
String macAddress;

uint32_t stableMacHash() {
  uint32_t hash = 2166136261u;
  for (size_t i = 0; i < macAddress.length(); ++i) {
    hash = (hash ^ static_cast<uint8_t>(macAddress[i])) * 16777619u;
  }
  return hash;
}

uint32_t restorationDelayMs() {
  return 5000u + stableMacHash() % 60000u;
}

bool compressorType(const String& type) {
  return type.startsWith("split_ac_") || type == "refrigerator";
}

void setRelay(uint8_t index, bool on) {
  if (index >= applianceCount) return;
  if (appliances[index].on == on) return;
  appliances[index].on = on;
  if (on && restoreCommandCount < kApplianceCount) {
    restoreCommands[restoreCommandCount++] = appliances[index].id;
  } else if (!on && shedCommandCount < kApplianceCount) {
    shedCommands[shedCommandCount++] = appliances[index].id;
  }
  if (kEnableLowVoltageOutputs) {
    digitalWrite(kRelayPins[index], on ? HIGH : LOW);
  }
}

void publishStatus(const char* messageType) {
  JsonDocument message;
  message["protocol_version"] = kProtocolVersion;
  message["message_type"] = messageType;
  message["sequence"] = txSequence++;
  message["building_id"] = buildingId;
  message["controller_status"] =
      millis() - lastMessageMs <= kCommunicationTimeoutMs ? "connected" : "autonomous";
  JsonObject states = message["appliance_states"].to<JsonObject>();
  for (uint8_t i = 0; i < applianceCount; ++i) {
    states[appliances[i].id] = appliances[i].on ? "ON" : "OFF";
  }
  JsonArray shed = message["shed_commands"].to<JsonArray>();
  for (uint8_t i = 0; i < shedCommandCount; ++i) shed.add(shedCommands[i]);
  JsonArray restore = message["restore_commands"].to<JsonArray>();
  for (uint8_t i = 0; i < restoreCommandCount; ++i) restore.add(restoreCommands[i]);
  shedCommandCount = 0;
  restoreCommandCount = 0;
  serializeJson(message, Serial);
  Serial.println();
}

void evaluateLocalPolicy() {
  const bool underFrequency =
      simulatedFrequencyHz <= kShedFrequencyHz || simulatedRoCoFHzPerS <= kShedRoCoFHzPerS;
  if (underFrequency) {
    stableSinceMs = 0;
    for (uint8_t i = 0; i < applianceCount; ++i) {
      Appliance& appliance = appliances[i];
      const bool essentialEmergency =
          simulatedFrequencyHz <= kEssentialShedFrequencyHz &&
          appliance.priority == "essential";
      if (appliance.enrolled &&
          (appliance.priority == "deferrable" || essentialEmergency) &&
          appliance.on) {
        setRelay(i, false);
        appliance.lastOffMs = millis();
      }
    }
    return;
  }

  if (simulatedFrequencyHz >= kRestoreFrequencyHz) {
    if (stableSinceMs == 0) stableSinceMs = millis();
    if (millis() - stableSinceMs >= restorationDelayMs() &&
        millis() - lastRestoreMs >= kRestoreSpacingMs) {
      for (uint8_t i = 0; i < applianceCount; ++i) {
        Appliance& appliance = appliances[i];
        const uint32_t minimumOffMs =
            compressorType(appliance.type) ? kCompressorLockoutMs : 0u;
        if (appliance.enrolled &&
            (appliance.priority == "deferrable" || appliance.priority == "essential") &&
            !appliance.on &&
            millis() - appliance.lastOffMs >= minimumOffMs) {
          setRelay(i, true);
          lastRestoreMs = millis();
          break;
        }
      }
    }
  } else {
    stableSinceMs = 0;
  }
}

void acceptTelemetry(JsonDocument& message) {
  const char* version = message["protocol_version"] | "";
  const char* type = message["message_type"] | "";
  const char* requestedBuilding = message["building_id"] | "";
  const uint32_t sequence = message["sequence"] | 0u;
  if (strcmp(version, kProtocolVersion) != 0 || strcmp(type, "telemetry") != 0 ||
      requestedBuilding[0] == '\0' ||
      (!buildingId.isEmpty() && requestedBuilding != buildingId) ||
      (haveSequence && sequence <= lastRxSequence)) {
    return;
  }
  if (buildingId.isEmpty()) buildingId = requestedBuilding;
  lastRxSequence = sequence;
  haveSequence = true;
  lastMessageMs = millis();
  simulatedFrequencyHz = message["frequency_hz"] | 50.0f;
  simulatedRoCoFHzPerS = message["rocof_hz_per_s"] | 0.0f;

  JsonArrayConst incoming = message["appliances"].as<JsonArrayConst>();
  for (JsonObjectConst item : incoming) {
    const String id = item["appliance_id"] | "";
    if (id.isEmpty()) continue;
    uint8_t index = 0;
    while (index < applianceCount && appliances[index].id != id) ++index;
    if (index == applianceCount) {
      if (applianceCount >= kApplianceCount) continue;
      appliances[index].id = id;
      const String reportedState = item["state"] | "ON";
      appliances[index].on = reportedState == "ON" || reportedState == "RUNNING";
      appliances[index].lastOffMs = appliances[index].on ? 0 : millis();
      ++applianceCount;
    }
    appliances[index].priority = item["priority"] | "deferrable";
    appliances[index].type = item["appliance_type"] | "";
    appliances[index].enrolled = item["enrolled"] | true;
  }
}

void readProtocolLine() {
  if (!Serial.available()) return;
  String line = Serial.readStringUntil('\n');
  JsonDocument message;
  if (deserializeJson(message, line)) return;
  acceptTelemetry(message);
}
}  // namespace

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(100);
  macAddress = WiFi.macAddress();
  lastMessageMs = millis();
  for (uint8_t pin : kRelayPins) {
    pinMode(pin, OUTPUT);
    digitalWrite(pin, LOW);
  }
}

void loop() {
  readProtocolLine();
  evaluateLocalPolicy();
  if (!buildingId.isEmpty() && millis() - lastHeartbeatMs >= kHeartbeatMs) {
    lastHeartbeatMs = millis();
    publishStatus("heartbeat");
  }
  delay(10);
}
