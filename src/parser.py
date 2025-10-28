# parser.py
# 这里放数据解析代码
# parser.py
# 按协议解析字节流：帧格式:
# [0xAA][0x55][LEN(1)][TYPE(1)][PAYLOAD..LEN bytes][CRC16 (2 bytes, little-endian)]
#
# TYPE == 0x01 -> ADC 数据：payload 为重复的 (sample_id:u16 LE, adc:u16 LE) 对
# 支持粘包/拆包，并返回解析好的样本列表。

from collections import deque
from typing import List, Dict
from utils import crc16_ccitt
import struct

HEADER = b'\xAA\x55'
HEADER_LEN = 2

class Parser:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data: bytes) -> List[Dict]:
        """
        Feed raw bytes, return list of parsed samples.
        Each parsed sample is a dict: {'timestamp': None, 'sample_id': int, 'adc': int, 'raw_frame': bytes}
        """
        self.buffer.extend(data)
        results = []

        # try to find frame start
        while True:
            if len(self.buffer) < HEADER_LEN + 1 + 1 + 2:  # header + len + type + crc
                break
            # find header
            idx = self.buffer.find(HEADER)
            if idx == -1:
                # drop all before possible header
                self.buffer.clear()
                break
            if idx > 0:
                # discard leading bytes
                del self.buffer[:idx]
            # now header at 0
            if len(self.buffer) < 4:
                break  # wait for len/type
            length = self.buffer[2]  # LEN byte
            total_len = HEADER_LEN + 1 + 1 + length + 2  # header + LEN + TYPE + payload + crc
            if len(self.buffer) < total_len:
                break  # wait for full frame
            frame = bytes(self.buffer[:total_len])
            # compute crc over LEN..PAYLOAD
            crc_field = frame[-2:]  # little-endian
            payload_for_crc = frame[2:-2]  # from LEN through payload inclusive
            calc = crc16_ccitt(payload_for_crc)
            recv_crc = struct.unpack('<H', crc_field)[0]
            if calc != recv_crc:
                # CRC fail -> discard header byte and resync
                # to avoid infinite loop, drop first byte and continue
                del self.buffer[0]
                continue
            # CRC OK -> parse TYPE & PAYLOAD
            typ = frame[3]
            payload = frame[4:-2]
            if typ == 0x01:
                # payload is multiple of 4 bytes: sample_id (u16 LE) + adc (u16 LE)
                n = len(payload) // 4
                for i in range(n):
                    off = i * 4
                    sample_id, adc = struct.unpack_from('<HH', payload, off)
                    results.append({
                        'sample_id': int(sample_id),
                        'adc': int(adc),
                        'raw_frame': frame,
                    })
            else:
                # unknown TYPE: return raw frame as single entry
                results.append({
                    'sample_id': None,
                    'adc': None,
                    'type': typ,
                    'raw_frame': frame,
                })
            # remove processed bytes
            del self.buffer[:total_len]
        return results
