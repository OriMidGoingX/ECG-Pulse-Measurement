# utils.py
# 这里放 CRC 等工具函数
# utils.py
# 辅助函数：CRC16-CCITT 等

def crc16_ccitt(data: bytes, poly: int = 0x1021, init_val: int = 0xFFFF) -> int:
    """
    CRC-16/CCITT-FALSE implementation
    Returns 16-bit integer.
    """
    crc = init_val
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) & 0xFFFF) ^ poly
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFFFF
