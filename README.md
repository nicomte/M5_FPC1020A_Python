# M5_FPC1020A

A Python driver for the M5Stack FPC1020A fingerprint sensor unit, communicating over UART. This is a
Python port of the methods exposed by M5's official [Arduino/C++ library](https://github.com/m5stack/M5-FPC1020A),
with one addition: `get_all_users()`, which is not present in the manufacturer's library.

## Hardware

Tested with the M5Stack Unit Finger (FPC1020A) connected via UART (default `/dev/serial0`, e.g. on a
Raspberry Pi).

## Dependencies

```bash
pip install -r requirements.txt
```

Or manually:

```bash
pip install pyserial
```

## Usage

```python
from M5_FPC1020A import M5_FPC1020A, enable_debug
from M5_FPC1020A_Domain import PermissionLevels, ScanNr, FingerRepeatMode

# Optional: verbose TX/RX logging
enable_debug()

sensor = M5_FPC1020A()
if not sensor.begin(19200):
    raise RuntimeError("Could not connect to sensor")

# Enroll a fingerprint (2-6 scans; see notes below)
sensor.add_fingerprint(user_id=1, permission=PermissionLevels.NORMAL, scan_nr=ScanNr.first)
sensor.add_fingerprint(user_id=1, permission=PermissionLevels.NORMAL, scan_nr=ScanNr.second)
...optional scans ScanNr.third through ScanNr.fifth...
sensor.add_fingerprint(user_id=1, permission=PermissionLevels.NORMAL, scan_nr=ScanNr.sixth)

# Match a finger against enrolled users
result = sensor.match_fingerprint_user_permission(timeout=8000)
if result.success:
    print(result.user_id, result.permission)
```

A minimal interactive CLI tester is included in `testfile.py`.

## Supported methods

This library currently covers the same functionality as M5's official library, plus one extra
read-only method:

| Method | Description |
|---|---|
| `begin(baud)` | Open the serial connection and verify the sensor responds |
| `set_baud(baud)` | Change and persist the sensor's UART baud rate |
| `get_user_count()` | Number of enrolled fingerprints |
| `get_all_users()` | **(not in the official library)** List all enrolled `(user_id, permission)` pairs |
| `add_fingerprint(user_id, permission, scan_nr)` | Enroll one scan of a fingerprint (call 2–6 times per user) |
| `del_fingerprint(user_id)` | Delete a single enrolled user |
| `del_all_fingerprints()` | Wipe all enrolled fingerprints |
| `match_fingerprint_user_permission(timeout)` | Scan and match a finger against enrolled users |
| `get_finger_id()` / `get_finger_permission()` | Read ID/permission from the last response buffer |
| `set_finger_mode(mode)` / `get_finger_mode()` | Get/set duplicate-fingerprint repeat mode |
| `sleep()` | Put the sensor into sleep mode. I do not know how to wake it up again, other than disconnecting the sensor. |

## Enrollment notes

- A fingerprint enrollment requires 2 to 6 scans, sent as commands `0x01 -> 0x02 (x0-4) -> 0x03`
  (`ScanNr.first`, `ScanNr.second`..`ScanNr.fifth`, `ScanNr.sixth`).
- `user_id` and `permission` must be identical across all scans of one enrollment.
- Valid `user_id` range is 1–4095 (0xFFF); this Python port supports the full 16-bit ID range
  unlike the official C++ library, which is limited to a single byte (0–255).
- The meaning of `permission` values (1/2/3 → GUEST/NORMAL/MASTER) is application-defined.
