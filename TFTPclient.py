#!/usr/bin/python3
"""
사용법 예시:

  # 파일 다운로드 (GET)
  python3 TFTPclient.py 127.0.0.1 get sample.txt

  # 파일 업로드 (PUT)
  python3 TFTPclient.py 127.0.0.1 put sendme.txt

  # 포트 변경 (기본 69가 아닐 때)
  python3 TFTPclient.py 127.0.0.1 get sample.txt -p 1069
"""

import socket
import argparse
import os
from struct import pack

# 기본 설정
DEFAULT_PORT = 69
BLOCK_SIZE = 512
DEFAULT_TRANSFER_MODE = "octet"

# TFTP opcode 정의
OPCODE = {
    "RRQ": 1,
    "WRQ": 2,
    "DATA": 3,
    "ACK": 4,
    "ERROR": 5,
}

# TFTP 에러 코드 메시지
ERROR_CODE = {
    0: "Not defined, see error message (if any).",
    1: "File not found.",
    2: "Access violation.",
    3: "Disk full or allocation exceeded.",
    4: "Illegal TFTP operation.",
    5: "Unknown transfer ID.",
    6: "File already exists.",
    7: "No such user.",
}


def send_rrq(filename, mode):
    """RRQ 패킷 전송: [opcode][filename][0][mode][0]"""
    fmt = f">h{len(filename)}sB{len(mode)}sB"
    rrq_message = pack(
        fmt,
        OPCODE["RRQ"],
        filename.encode("utf-8"),
        0,
        mode.encode("utf-8"),
        0,
    )
    sock.sendto(rrq_message, server_address)
    print("보낸 RRQ:", rrq_message)


def send_wrq(filename, mode):
    """WRQ 패킷 전송: [opcode][filename][0][mode][0]"""
    fmt = f">h{len(filename)}sB{len(mode)}sB"
    wrq_message = pack(
        fmt,
        OPCODE["WRQ"],
        filename.encode("utf-8"),
        0,
        mode.encode("utf-8"),
        0,
    )
    sock.sendto(wrq_message, server_address)
    print("보낸 WRQ:", wrq_message)


def send_ack(block_num, server):
    """ACK 패킷 전송: [opcode][block 번호]"""
    ack_message = pack(">HH", OPCODE["ACK"], block_num)
    sock.sendto(ack_message, server)
    print("보낸 ACK 블록:", block_num)


# -----------------------------
# GET 동작 (다운로드)
# -----------------------------
def tftp_get(filename, mode):
    # RRQ 보내기
    send_rrq(filename, mode)

    # 로컬에 저장할 파일 열기 (덮어씀)
    f = open(filename, "wb")
    expected_block_number = 1
    server_new_addr = None

    while True:
        try:
            data, addr = sock.recvfrom(4 + BLOCK_SIZE)
        except socket.timeout:
            print("서버 응답이 없습니다. (GET 타임아웃)")
            f.close()
            return

        opcode = int.from_bytes(data[:2], "big")

        # 처음 받은 패킷의 출처(포트)를 이후 전송용 주소로 사용
        if server_new_addr is None:
            server_new_addr = addr

        # DATA 패킷
        if opcode == OPCODE["DATA"]:
            block_number = int.from_bytes(data[2:4], "big")
            file_block = data[4:]

            if block_number == expected_block_number:
                f.write(file_block)
                send_ack(block_number, server_new_addr)
                expected_block_number += 1
                try:
                    print("수신 데이터:", file_block.decode())
                except UnicodeDecodeError:
                    # 바이너리 파일일 수도 있으니 무시
                    pass
            else:
                # 중복 블록 → ACK만 다시 보냄
                send_ack(block_number, server_new_addr)

            # 마지막 블록(512보다 작으면 종료)
            if len(file_block) < BLOCK_SIZE:
                f.close()
                print("다운로드 완료, 마지막 블록 크기:", len(file_block))
                break

        # ERROR 패킷
        elif opcode == OPCODE["ERROR"]:
            error_code = int.from_bytes(data[2:4], "big")
            print("TFTP ERROR:", ERROR_CODE.get(error_code, "Unknown error"))
            f.close()
            break

        else:
            print("알 수 없는 opcode 수신(GET):", opcode)
            f.close()
            break


# -----------------------------
# PUT 동작 (업로드)
# -----------------------------
def tftp_put(filename, mode):
    # 로컬에 파일이 있는지 확인
    if not os.path.exists(filename):
        print("로컬에 업로드할 파일이 없습니다:", filename)
        return

    # WRQ 보내기
    send_wrq(filename, mode)

    # 서버의 ACK(0블록) 또는 ERROR 기다리기
    try:
        data, addr = sock.recvfrom(4 + BLOCK_SIZE)
    except socket.timeout:
        print("서버 응답이 없습니다. (WRQ 타임아웃)")
        return

    opcode = int.from_bytes(data[:2], "big")

    if opcode == OPCODE["ERROR"]:
        error_code = int.from_bytes(data[2:4], "big")
        print("TFTP ERROR:", ERROR_CODE.get(error_code, "Unknown error"))
        return

    if opcode != OPCODE["ACK"]:
        print("WRQ 이후 ACK를 받지 못했습니다. opcode:", opcode)
        return

    ack_block = int.from_bytes(data[2:4], "big")
    if ack_block != 0:
        print("WRQ 이후 ACK 블록 번호가 0이 아닙니다:", ack_block)
        return

    # 이후 DATA/ACK는 새로운 포트(addr)와 통신
    server_new_addr = addr

    # 실제 파일 전송
    with open(filename, "rb") as f:
        block_num = 1
        while True:
            chunk = f.read(BLOCK_SIZE)
            # 항상 DATA 패킷은 한 번은 보냄 (빈 파일이면 0바이트 DATA)
            data_packet = pack(">HH", OPCODE["DATA"], block_num) + chunk
            sock.sendto(data_packet, server_new_addr)
            print(f"보낸 DATA 블록: {block_num}, 크기: {len(chunk)}")

            # ACK 기다리기
            try:
                data, addr = sock.recvfrom(4 + BLOCK_SIZE)
            except socket.timeout:
                print("ACK 대기 중 타임아웃 발생.")
                return

            opcode = int.from_bytes(data[:2], "big")

            if opcode == OPCODE["ACK"]:
                ack_block = int.from_bytes(data[2:4], "big")
                if ack_block != block_num:
                    print("잘못된 ACK 블록 번호 수신:", ack_block)
                    return

                # 마지막 블록(512보다 작은 경우)이면 종료
                if len(chunk) < BLOCK_SIZE:
                    print("업로드 완료, 마지막 블록:", block_num)
                    break

                block_num += 1

            elif opcode == OPCODE["ERROR"]:
                error_code = int.from_bytes(data[2:4], "big")
                print("TFTP ERROR:", ERROR_CODE.get(error_code, "Unknown error"))
                return
            else:
                print("알 수 없는 opcode 수신(PUT):", opcode)
                return


# -----------------------------
# 1) 명령행 인자 처리
# -----------------------------
parser = argparse.ArgumentParser(description="TFTP client program")
parser.add_argument("host", help="Server IP address", type=str)
parser.add_argument("operation", help="get or put a file", type=str)
parser.add_argument("filename", help="name of file to transfer", type=str)
parser.add_argument("-p", "--port", dest="port", type=int)
args = parser.parse_args()

# -----------------------------
# 2) 소켓 / 서버 정보 설정
# -----------------------------
server_ip = args.host
if args.port is None:
    server_port = DEFAULT_PORT
else:
    server_port = args.port

server_address = (server_ip, server_port)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(5.0)  # RRQ/WRQ 및 DATA/ACK 타임아웃

mode = DEFAULT_TRANSFER_MODE  # "octet" 고정
operation = args.operation.lower()
filename = args.filename

# -----------------------------
# 3) get / put 동작 분기
# -----------------------------
if operation == "get":
    tftp_get(filename, mode)
elif operation == "put":
    tftp_put(filename, mode)
else:
    print("get 또는 put 중 하나만 사용할 수 있습니다.")

sock.close()
