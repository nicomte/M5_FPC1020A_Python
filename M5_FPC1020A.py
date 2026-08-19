import M5_FPC1020A_CMD as cmd
from M5_FPC1020A_Domain import BaudRate, FingerRepeatMode, PermissionLevels, ScanNr, MatchResult
from serial.serialutil import EIGHTBITS, PARITY_NONE, STOPBITS_ONE
from serial import Serial
from time import time,sleep
import logging

logger = logging.getLogger(__name__)


def enable_debug() -> bool:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )
    return True


class M5_FPC1020A:
    def __init__(self):
        self._serial: Serial | None = None
        self._enable_debug = False
        self._tx_buf = bytearray(9)
        self._rx_buf = bytearray(9)

    def begin(self, baud: int) -> bool:
        self._serial = Serial(port='/dev/serial0', baudrate=baud, timeout=3, bytesize=EIGHTBITS, parity=PARITY_NONE, stopbits=STOPBITS_ONE)

        user_count = self.get_user_count()

        if user_count == cmd.ACK_FAIL:
            logger.warning("Sensor test failed, (%02X)", cmd.ACK_FAIL)
            return False
        else:
            return True

    def set_baud(self, baud: int) -> bool:
        self._tx_buf[cmd.CMD] = cmd.CMD_BAUD
        self._tx_buf[cmd.P1] = 0
        self._tx_buf[cmd.P2] = 0

        match baud:
            case 9600:
                self._tx_buf[cmd.P3] = BaudRate.BAUD_9600
            case 19200:
                self._tx_buf[cmd.P3] = BaudRate.BAUD_19200
            case 38400:
                self._tx_buf[cmd.P3] = BaudRate.BAUD_38400
            case 57600:
                self._tx_buf[cmd.P3] = BaudRate.BAUD_57600
            case 115200:
                self._tx_buf[cmd.P3] = BaudRate.BAUD_115200
            case _:
                return False

        old_baud = self._serial.baudrate
        old_port = self._serial.port
        # Changing BAUD-Rate can cause the sensor to send malformed frames. This function cannot trust send_cmd's response
        self.__send_cmd(1500)
        self._serial.close()
        sleep(0.2)  # let the module settle into the new baud

        # Create new serial connection with updated BAUD-Rate
        self._serial = Serial(
            port=old_port, baudrate=baud, timeout=3,
            bytesize=EIGHTBITS, parity=PARITY_NONE, stopbits=STOPBITS_ONE,
        )

        # 3 tries to check if new BAUD-Rate is working
        for _ in range(3):
            if self.get_user_count() != cmd.ACK_FAIL:
                logger.info("Baud rate changed to %d", baud)
                return True
            sleep(0.1)

        # BAUD-Rate change did not complete, restarting serial connection with old values
        logger.warning("Baud change to %d did not verify, reverting", baud)
        self._serial.close()
        self._serial = Serial(
            port=old_port, baudrate=old_baud, timeout=3,
            bytesize=EIGHTBITS, parity=PARITY_NONE, stopbits=STOPBITS_ONE,
        )
        return False

    def __send_cmd(self, timeout: int):
        checksum = 0
        self._tx_buf[5] = 0
        self._serial.reset_input_buffer()
        self._serial.write(bytes([cmd.CMD_HEAD]))
        logger.debug("Send start: %02X", cmd.CMD_HEAD)

        for byte in self._tx_buf[1:6]:
            self._serial.write(bytes([byte]))
            logger.debug("TX: %02X", byte)
            checksum ^= byte

        self._serial.write(bytes([checksum]))
        self._serial.write(bytes([cmd.CMD_TAIL]))
        logger.debug("Checksum: %02X", checksum)
        logger.debug("Send end: %02X", cmd.CMD_TAIL)

        # Response
        start = int(time() * 1000)
        index = 0
        logger.debug("Receive start:")
        self._rx_buf = bytearray(9)

        while 1:
            if self._serial.in_waiting > 0:
                ch = self._serial.read(1)[0]
                self._rx_buf[index] = ch
                logger.debug("RX: %02X", ch)
                if self._rx_buf[0] == cmd.CMD_HEAD:
                    if index < 7:
                        index += 1
                else:
                    index = 0

                if self._rx_buf[0] == cmd.CMD_HEAD and self._rx_buf[7] == cmd.CMD_TAIL:
                    break
            elif int(time() * 1000) - start > timeout:
                break

        logger.debug("Receive end:")

        if self._rx_buf[cmd.HEAD] != cmd.CMD_HEAD: return cmd.ACK_FAIL
        if self._rx_buf[cmd.TAIL] != cmd.CMD_TAIL: return cmd.ACK_FAIL
        if self._rx_buf[cmd.CMD] != self._tx_buf[cmd.CMD]: return cmd.ACK_FAIL

        checksum = 0
        for j in range(1, cmd.CHK):
            checksum ^= self._rx_buf[j]
        if checksum != self._rx_buf[cmd.CHK]:
            return cmd.ACK_FAIL
        return cmd.ACK_SUCCESS

    def __read_data_packet(self, timeout: int) -> bytes | None:
        packet_length = (self._rx_buf[cmd.Q1] << 8) | self._rx_buf[cmd.Q2]
        start = int(time() * 1000)
        logger.debug("Receive start data packet:")
        total = packet_length + 3
        data_packet = bytearray(total)

        # Phase 1: sync to header byte
        while True:
            if (int(time() * 1000) - start) > timeout:
                logger.warning("Timeout waiting for packet header")
                return None
            elif self._serial.in_waiting == 0:
                continue
            else:
                ch = self._serial.read(1)[0]
                logger.debug("Packet head candidate: %02X", ch)
                if ch == cmd.CMD_HEAD:
                    data_packet[0] = ch
                    break

        # Phase 2: read the body now that header is confirmed
        for i in range(1, total):
            if (int(time() * 1000) - start) > timeout:
                logger.warning("Timeout mid-packet at byte %d of %d", i, total)
                return None
            chunk = self._serial.read(1)
            if len(chunk) == 0:
                logger.warning("Serial read returned empty at byte %d of %d", i, total)
                return None
            data_packet[i] = chunk[0]

        logger.debug("Receive end data packet:")

        if data_packet[0] != cmd.CMD_HEAD:
            logger.warning("Packet head mismatch: expected %02X got %02X",cmd.CMD_HEAD, data_packet[0])
            return None
        if data_packet[-1] != cmd.CMD_TAIL:
            logger.warning("Packet tail mismatch: expected %02X got %02X",cmd.CMD_TAIL, data_packet[-1])
            return None

        checksum = 0
        for j in range(1, len(data_packet)-2):
            checksum ^= data_packet[j]
        if checksum != data_packet[-2]:
            return None
        # First three entries are CMD_HEAD, user_count (high) and user_count (low). Since only the user_id and permission are needed, the first three entries are dropped. Second to last is the checksum and the last byte is the Tail identifier.
        return bytes(data_packet[3:-2])

    def get_all_users(self) -> list[tuple[int, int]] | None:
        self._tx_buf[cmd.CMD] = cmd.CMD_GET_ALL
        self._tx_buf[cmd.P1] = 0
        self._tx_buf[cmd.P2] = 0
        self._tx_buf[cmd.P3] = 0

        res = self.__send_cmd(3000)

        if res != cmd.ACK_SUCCESS or self._rx_buf[cmd.Q3] != cmd.ACK_SUCCESS:
            logger.warning("Failed to get all users")
            return None

        data_packet = self.__read_data_packet(3000)

        if data_packet is None:
            logger.warning("Failed to get any users")
            return None

        if len(data_packet) % 3 != 0:
            logger.warning("User info records malformed")
            return None

        user_data = []
        user_id_low = 0
        user_id_high = 0
        permission = 0

        for i in range(len(data_packet)):
            match i % 3:
                case 0:
                    user_id_high = data_packet[i]
                case 1:
                    user_id_low = data_packet[i]
                case 2:
                    permission = data_packet[i]
                    user_data.append((user_id_high << 8 | user_id_low, permission))

        return user_data

    def sleep(self) -> bool:
        self._tx_buf[cmd.CMD] = cmd.CMD_SLEEP_MODE
        self._tx_buf[cmd.P1] = 0
        self._tx_buf[cmd.P2] = 0
        self._tx_buf[cmd.P3] = 0


        res = self.__send_cmd(1500)
        if res == cmd.ACK_SUCCESS:
            return True
        else:
            return False

    def set_finger_mode(self, mode: FingerRepeatMode) -> int:
        self._tx_buf[cmd.CMD] = cmd.CMD_ADD_MODE
        self._tx_buf[cmd.P1] = 0
        self._tx_buf[cmd.P2] = mode
        self._tx_buf[cmd.P3] = 0


        res = self.__send_cmd(1200)
        if res == cmd.ACK_SUCCESS and self._rx_buf[cmd.Q3] == cmd.ACK_SUCCESS:
            return cmd.ACK_SUCCESS
        else:
            return cmd.ACK_FAIL

    def get_finger_mode(self) -> int:
        self._tx_buf[cmd.CMD] = cmd.CMD_ADD_MODE
        self._tx_buf[cmd.P1] = 0
        self._tx_buf[cmd.P2] = 0
        self._tx_buf[cmd.P3] = 0x01

        res = self.__send_cmd(1200)

        if res == cmd.ACK_SUCCESS:
            return self._rx_buf[cmd.Q2]
        else:
            return cmd.ACK_FAIL

    def get_user_count(self) -> int:
        self._tx_buf[cmd.CMD] = cmd.CMD_USER_CNT
        self._tx_buf[cmd.P1] = 0
        self._tx_buf[cmd.P2] = 0
        self._tx_buf[cmd.P3] = 0

        res = self.__send_cmd(1200)

        if res == cmd.ACK_SUCCESS and self._rx_buf[cmd.Q3] == cmd.ACK_SUCCESS:
            return self._rx_buf[cmd.Q1] << 8 | self._rx_buf[cmd.Q2]
        else:
            return cmd.ACK_FAIL

    def del_all_fingerprints(self) -> int:
        self._tx_buf[cmd.CMD] = cmd.CMD_DEL_ALL
        self._tx_buf[cmd.P1] = 0
        self._tx_buf[cmd.P2] = 0
        self._tx_buf[cmd.P3] = 0

        res = self.__send_cmd(1200)

        if res == cmd.ACK_SUCCESS and self._rx_buf[cmd.Q3] == cmd.ACK_SUCCESS:
            return cmd.ACK_SUCCESS
        else:
            return cmd.ACK_FAIL

    def del_fingerprint(self, user_id: int) -> int:
        low_byte = user_id & 0xFF
        high_byte = (user_id >> 8) & 0xFF

        self._tx_buf[cmd.CMD] = cmd.CMD_DEL
        self._tx_buf[cmd.P1] = high_byte
        self._tx_buf[cmd.P2] = low_byte
        self._tx_buf[cmd.P3] = 0

        res = self.__send_cmd(1200)

        if res == cmd.ACK_SUCCESS and self._rx_buf[cmd.Q3] == cmd.ACK_SUCCESS:
            return cmd.ACK_SUCCESS
        else:
            return cmd.ACK_FAIL

    def add_fingerprint(self, user_id: int, timeout: int, permission: PermissionLevels, scan_nr: ScanNr) -> int:
        self._tx_buf[cmd.CMD] = scan_nr

        low_byte = user_id & 0xFF
        high_byte = (user_id >> 8) & 0xFF

        self._tx_buf[cmd.P1] = high_byte
        self._tx_buf[cmd.P2] = low_byte
        self._tx_buf[cmd.P3] = permission

        res = self.__send_cmd(timeout)

        if res == cmd.ACK_SUCCESS and self._rx_buf[cmd.Q3] == cmd.ACK_SUCCESS:
            return cmd.ACK_SUCCESS
        elif self._rx_buf[cmd.Q3] == cmd.ACK_TIMEOUT:
            return cmd.ACK_TIMEOUT
        elif self._rx_buf[cmd.Q3] == cmd.ACK_FULL:
            return cmd.ACK_FULL
        elif self._rx_buf[cmd.Q3] == cmd.ACK_USER_EXIST:
            return cmd.ACK_USER_EXIST
        else:
            return cmd.ACK_FAIL

    def match_fingerprint_user_permission(self, timeout: int) -> MatchResult:
        self._tx_buf[cmd.CMD] = cmd.CMD_MATCH
        self._tx_buf[cmd.P1] = 0
        self._tx_buf[cmd.P2] = 0
        self._tx_buf[cmd.P3] = 0

        res = self.__send_cmd(timeout)
        if res == cmd.ACK_SUCCESS and 1 <= self._rx_buf[cmd.Q3] <= 3:
            user_id = (self._rx_buf[cmd.Q1] << 8) | self._rx_buf[cmd.Q2]
            permission = self._rx_buf[cmd.Q3]

            return MatchResult(
                success=True,
                user_id=user_id,
                permission=PermissionLevels(permission),
                ack_code=res,
            )
        else:
            return MatchResult(
                success=False,
                ack_code=res,
            )

    def get_finger_id(self) -> int:
        return self._rx_buf[cmd.Q1] << 8 | self._rx_buf[cmd.Q2]

    def get_finger_permission(self) -> int:
        return self._rx_buf[cmd.Q3]
