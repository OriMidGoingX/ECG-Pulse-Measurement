# virtual_sender.py
# 这里放虚拟发送器示例代码
# virtual_sender.py
# 用于测试：向某个串口发送协议帧（可以发送 N 个样点打包在一个帧里）
# 使用示例（在另一个终端运行）:
# python virtual_sender.py COM5 115200 --rate 100 --samples-per-frame 5
#
# 注意：在 Windows 上通常需要先安装一个虚拟串口对（com0com / VSPE），
# 使得 sender 端口和上位机端口成对出现（比如 COM5 <-> COM6）。

import sys
import time
import struct
import argparse
import serial
from utils import crc16_ccitt

HEADER = b'\xAA\x55'

def make_frame(samples):
    # samples: list of (sample_id:int, adc:int)
    payload = bytearray()
    for sid, adc in samples:
        payload += struct.pack('<HH', sid & 0xFFFF, adc & 0xFFFF)
    length = len(payload) + 0  # payload length (TYPE byte separate)
    typ = 0x01
    # frame = header + LEN + TYPE + payload + CRC16(LEN..payload)
    header_and_len_type_payload = bytearray()
    header_and_len_type_payload += bytes([length])
    header_and_len_type_payload += bytes([typ])
    header_and_len_type_payload += payload
    crc = crc16_ccitt(header_and_len_type_payload)
    frame = HEADER + header_and_len_type_payload + struct.pack('<H', crc)
    return frame

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('port', help='串口号，例如 COM5 或 /dev/ttyS1')
    parser.add_argument('baud', type=int, help='波特率，例如 115200')
    parser.add_argument('--rate', type=int, default=100, help='发送速率 (samples/s)')
    parser.add_argument('--samples-per-frame', type=int, default=1, help='每帧包含样点数')
    parser.add_argument('--max-adc', type=int, default=1023, help='adc 最大值')
    args = parser.parse_args()

    try:
        ser = serial.Serial(args.port, args.baud, timeout=1)
    except Exception as e:
        print("打开串口失败:", e)
        sys.exit(1)

    print(f"开始发送到 {args.port} @ {args.baud}. 速率 {args.rate} sps, 每帧 {args.samples_per_frame} samples")
    sample_id = 0
    try:
        interval = 1.0 / args.rate
        while True:
            samples = []
            for _ in range(args.samples_per_frame):
                sample_id = (sample_id + 1) & 0xFFFF
                # 模拟一个简单的正弦或渐变信号，这里用 saw
                adc = int((sample_id % (args.max_adc + 1)))
                samples.append((sample_id, adc))
            frame = make_frame(samples)
            ser.write(frame)
            # optional: flush for demo
            ser.flush()
            time.sleep(interval * args.samples_per_frame)
    except KeyboardInterrupt:
        print("停止发送")
    finally:
        ser.close()

if __name__ == '__main__':
    main()
