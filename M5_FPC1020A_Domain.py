from enum import IntEnum
from dataclasses import dataclass
import M5_FPC1020A_CMD as cmd

class BaudRate(IntEnum):
    BAUD_9600 = 1
    BAUD_19200 = 2
    BAUD_38400 = 3
    BAUD_57600 = 4
    BAUD_115200 = 5

class FingerRepeatMode(IntEnum):
    FINGER_NOT_REPEAT = 1
    FINGER_ALLOW_REPEAT = 0

class PermissionLevels(IntEnum):
    GUEST = cmd.ACK_GUEST_USER
    NORMAL = cmd.ACK_NORMAL_USER
    MASTER = cmd.ACK_MASTER_USER

class ScanNr(IntEnum):
    first = cmd.CMD_ADD_1
    second = cmd.CMD_ADD_2
    third = cmd.CMD_ADD_2
    fourth = cmd.CMD_ADD_2
    fifth = cmd.CMD_ADD_2
    sixth = cmd.CMD_ADD_3

@dataclass
class MatchResult:
    success: bool
    user_id: int | None = None
    permission: PermissionLevels | None = None
    ack_code: int | None = None