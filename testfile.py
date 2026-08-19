#!/usr/bin/env python3
"""
Minimaler interaktiver Tester für M5_FPC1020A auf Raspberry Pi.
Starten: python3 test_fpc1020a.py
"""

import sys
import time
import logging
from M5_FPC1020A import M5_FPC1020A, enable_debug
from M5_FPC1020A_Domain import PermissionLevels, ScanNr, FingerRepeatMode
import M5_FPC1020A_CMD as cmd

# Logging sofort aktivieren – dann siehst du alle TX/RX-Bytes
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("FPC1020A_Test")


class SensorTester:
    def __init__(self, port: str = "/dev/serial0", baud: int = 19200):
        self.sensor = M5_FPC1020A()
        self.port = port
        self.baud = baud
        self.connected = False

    def connect(self) -> bool:
        log.info(f"Öffne {self.port} @ {self.baud} baud …")
        try:
            ok = self.sensor.begin(self.baud)
            # WICHTIG: begin() prüft aktuell nur get_user_count() != 0xFF.
            # Das ist problematisch (siehe Hinweise unten). Wir machen einen
            # zusätzlichen Sanity-Check:
            count = self.sensor.get_user_count()
            if count == cmd.ACK_FAIL:
                log.error("Sensor antwortet nicht korrekt (get_user_count() == ACK_FAIL)")
                return False
            log.info(f"Verbunden. Aktuelle User-Anzahl: {count}")
            self.connected = True
            return True
        except Exception as e:
            log.error(f"Verbindungsfehler: {e}")
            return False

    def disconnect(self):
        if self.sensor._serial and self.sensor._serial.is_open:
            self.sensor._serial.close()
            log.info("Seriell geschlossen.")
        self.connected = False

    # ------------------------------------------------------------------
    # Einzelne Testmethoden – kannst du auch direkt in der Python-Shell
    # aufrufen, ohne das Menü zu nutzen.
    # ------------------------------------------------------------------

    def test_user_count(self):
        log.info("--- TEST: get_user_count() ---")
        count = self.sensor.get_user_count()
        if count == cmd.ACK_FAIL:
            log.error("✗ Fehlgeschlagen")
        else:
            log.info(f"✓ Anzahl gespeicherter Fingerabdrücke: {count}")

    def test_list_users(self):
        log.info("--- TEST: get_all_users() ---")
        users = self.sensor.get_all_users()
        if users is None:
            log.error("✗ Fehlgeschlagen oder keine Antwort")
            return
        if not users:
            log.info("✓ Keine User vorhanden")
            return
        log.info(f"✓ {len(users)} User gefunden:")
        for uid, perm in users:
            p_name = PermissionLevels(perm).name if perm in (1, 2, 3) else f"UNK({perm})"
            log.info(f"    ID={uid:<5} (0x{uid:04X}) | Berechtigung={p_name}")

    def test_enroll(self):
        log.info("--- TEST: add_fingerprint() ---")
        try:
            uid = int(input("User-ID (0-65535): ").strip())
            perm = int(input("Berechtigung (1=GUEST, 2=NORMAL, 3=MASTER): ").strip())
        except ValueError:
            log.error("Ungültige Eingabe")
            return

        permission = PermissionLevels(perm)

        # Der Sensor braucht typischerweise 3 Scans: ADD_1, ADD_2, ADD_3
        scans = [
            (ScanNr.first,  "1. Scan – Finger auflegen …"),
            (ScanNr.second, "2. Scan – Finger erneut auflegen …"),
            (ScanNr.sixth,  "3. Scan – Finger letztes Mal auflegen …"),
        ]

        for scan_cmd, msg in scans:
            input(f"\n{msg} (Enter drücken, dann Finger halten)")
            res = self.sensor.add_fingerprint(uid, 8000, permission, scan_cmd)
            if res == cmd.ACK_SUCCESS:
                log.info("  ✓ Scan OK")
            elif res == cmd.ACK_TIMEOUT:
                log.error("  ✗ Timeout – kein Finger erkannt")
                return
            elif res == cmd.ACK_FULL:
                log.error("  ✗ Speicher voll")
                return
            elif res == cmd.ACK_USER_EXIST:
                log.error("  ✗ User-ID existiert bereits")
                return
            else:
                log.error(f"  ✗ Fehler: 0x{res:02X}")
                return

        log.info(f"✓ Fingerabdruck für User {uid} erfolgreich angelegt.")

    def test_match(self):
        log.info("--- TEST: match_fingerprint_user_permission() ---")
        log.info("Finger auf Sensor halten …")
        result = self.sensor.match_fingerprint_user_permission(timeout=8000)
        if result.success:
            log.info(f"✓ Treffer!")
            log.info(f"    User-ID:      {result.user_id} (0x{result.user_id:04X})")
            log.info(f"    Berechtigung: {result.permission.name}")
        else:
            log.error(f"✗ Kein Treffer (ack_code=0x{result.ack_code:02X})")

    def test_delete_one(self):
        log.info("--- TEST: del_fingerprint() ---")
        try:
            uid = int(input("Zu löschende User-ID: ").strip())
        except ValueError:
            log.error("Ungültige Eingabe")
            return
        res = self.sensor.del_fingerprint(uid)
        if res == cmd.ACK_SUCCESS:
            log.info(f"✓ User {uid} gelöscht")
        else:
            log.error(f"✗ Fehler: 0x{res:02X}")

    def test_delete_all(self):
        log.info("--- TEST: del_all_fingerprints() ---")
        confirm = input("⚠️  ALLE Fingerabdrücke löschen? 'yes' eingeben: ").strip().lower()
        if confirm != "yes":
            log.info("Abgebrochen")
            return
        res = self.sensor.del_all_fingerprints()
        if res == cmd.ACK_SUCCESS:
            log.info("✓ Alle Fingerabdrücke gelöscht")
        else:
            log.error(f"✗ Fehler: 0x{res:02X}")

    def test_baud(self):
        log.info("--- TEST: set_baud() ---")
        print("Verfügbar: 9600, 19200, 38400, 57600, 115200")
        try:
            new_baud = int(input("Neue Baudrate: ").strip())
        except ValueError:
            log.error("Ungültige Eingabe")
            return
        ok = self.sensor.set_baud(new_baud)
        if ok:
            self.baud = new_baud
            log.info(f"✓ Baudrate geändert. Verbindung wurde neu aufgebaut.")
        else:
            log.error("✗ Baudrate-Änderung fehlgeschlagen")

    def test_sleep(self):
        log.info("--- TEST: sleep() ---")
        if self.sensor.sleep():
            log.info("✓ Sleep-Befehl gesendet")
        else:
            log.error("✗ Sleep-Befehl fehlgeschlagen")

    def test_finger_mode(self):
        log.info("--- TEST: Finger-Repeat-Mode ---")
        current = self.sensor.get_finger_mode()
        if current == cmd.ACK_FAIL:
            log.error("✗ Konnte aktuellen Modus nicht lesen")
            return
        log.info(f"Aktueller Modus: 0x{current:02X}")
        try:
            mode = int(input("Neuer Modus (0=ALLOW_REPEAT, 1=NOT_REPEAT): ").strip())
        except ValueError:
            log.error("Ungültige Eingabe")
            return
        res = self.sensor.set_finger_mode(FingerRepeatMode(mode))
        if res == cmd.ACK_SUCCESS:
            log.info("✓ Modus gesetzt")
        else:
            log.error("✗ Fehler beim Setzen")


def print_menu():
    print("\n" + "=" * 50)
    print("  FPC1020A – Interaktiver Hardware-Test")
    print("=" * 50)
    print("  1. Verbinden")
    print("  2. User-Anzahl abfragen")
    print("  3. Alle User auflisten")
    print("  4. Fingerabdruck anlernen (enroll)")
    print("  5. Fingerabdruck erkennen (match)")
    print("  6. Einzelnen User löschen")
    print("  7. ALLE User löschen")
    print("  8. Baudrate ändern")
    print("  9. Sleep-Modus")
    print(" 10. Finger-Repeat-Mode setzen")
    print("  d. Debug-Logging togglen (NICHT implementiert – immer an)")
    print("  0. Beenden")
    print("=" * 50)


def main():
    tester = SensorTester()

    while True:
        print_menu()
        choice = input("Auswahl: ").strip()

        if choice == "0":
            tester.disconnect()
            print("Tschüss!")
            break

        elif choice == "1":
            tester.connect()

        elif choice in ("2", "3", "4", "5", "6", "7", "8", "9", "10"):
            if not tester.connected:
                print("Bitte zuerst verbinden (1)!")
                continue
            {
                "2": tester.test_user_count,
                "3": tester.test_list_users,
                "4": tester.test_enroll,
                "5": tester.test_match,
                "6": tester.test_delete_one,
                "7": tester.test_delete_all,
                "8": tester.test_baud,
                "9": tester.test_sleep,
                "10": tester.test_finger_mode,
            }[choice]()

        else:
            print("Ungültige Eingabe")

        input("\nEnter drücken zum Fortfahren …")


if __name__ == "__main__":
    main()
