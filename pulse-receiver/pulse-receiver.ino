const byte interruptPin = 2;
volatile bool sendFlag = false;
volatile unsigned long lastInterruptTime = 0; // Tracks last interrupt time
const unsigned long debounceDelay = 200;     // milliseconds

void setup() {
  Serial.begin(9600);
  pinMode(interruptPin, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(interruptPin), handleChange, CHANGE);
}

void loop() {
  if (sendFlag) {
    Serial.println("1");
    sendFlag = false;
  }
}

void handleChange() {
  unsigned long currentTime = millis();
  if (currentTime - lastInterruptTime > debounceDelay) {
    sendFlag = true;
    lastInterruptTime = currentTime;
  }
}
