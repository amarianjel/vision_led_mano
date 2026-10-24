/* Mano + 5 LED: bits 0..4 => D2..D6. 115200 baudios. */
const byte LED_PINS[5] = {2, 3, 4, 5, 6};
unsigned long ultimoMensaje = 0;
const unsigned long TIMEOUT_MS = 1500;
void apagar() { for (byte i=0;i<5;i++) digitalWrite(LED_PINS[i], LOW); }
void setup() {
  Serial.begin(115200);
  for (byte i=0;i<5;i++) pinMode(LED_PINS[i], OUTPUT);
  apagar(); ultimoMensaje=millis();
}
void loop() {
  while (Serial.available() > 0) {
    byte mascara = (byte)Serial.read();
    if (mascara <= 31) {
      for(byte i=0;i<5;i++) digitalWrite(LED_PINS[i], (mascara & (1 << i)) ? HIGH : LOW);
      ultimoMensaje=millis();
    }
  }
  if (millis() - ultimoMensaje > TIMEOUT_MS) apagar();
}
