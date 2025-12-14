TFTPclient.py 코드 동작 설명 (간단/쉬운 버전)
================================================

1) 이 프로그램은 뭐 하는 코드인가?
- TFTP(Trivial File Transfer Protocol) 클라이언트입니다.
- 서버(tftpd-hpa 등)와 UDP로 통신하면서 파일을:
  - get: 서버에서 다운로드
  - put: 서버로 업로드
- 전송 모드는 octet(바이너리)만 사용합니다.

------------------------------------------------
2) 실행(사용) 방법
- 다운로드(GET)
  python3 TFTPclient.py 127.0.0.1 get sample.txt

- 업로드(PUT)
  python3 TFTPclient.py 127.0.0.1 put sendme.txt

- 서버 포트가 69가 아닐 때 (-p 옵션)
  python3 TFTPclient.py 127.0.0.1 get sample.txt -p 1069

------------------------------------------------
3) 코드가 실행되는 전체 흐름(중요)
(1) 명령행 인자 읽기
- argparse로 host / operation(get|put) / filename / port(-p)를 받습니다.

(2) 서버 주소와 소켓 준비
- server_address = (서버IP, 포트)
- UDP 소켓(sock)을 만들고 sock.settimeout(5.0)으로 타임아웃을 둡니다.
  → 서버가 응답이 없을 때 무한 대기하지 않게 합니다.

(3) operation 값에 따라 분기
- get이면 tftp_get(filename, mode) 실행
- put이면 tftp_put(filename, mode) 실행
- 끝나면 sock.close()로 소켓 닫기

------------------------------------------------
4) TFTP 패킷 구조(이 코드에서 쓰는 형태)
TFTP는 2바이트 opcode로 패킷 종류를 구분합니다.

- RRQ(읽기 요청, opcode=1)
  [opcode(2)][filename][0][mode][0]

- WRQ(쓰기 요청, opcode=2)
  [opcode(2)][filename][0][mode][0]

- DATA(opcode=3)
  [opcode(2)][block(2)][data(0~512bytes)]

- ACK(opcode=4)
  [opcode(2)][block(2)]

- ERROR(opcode=5)
  [opcode(2)][errorcode(2)][errormsg][0]

코드에서는 struct.pack()을 이용해 위 구조대로 바이트(bytes)로 만들어서 sendto()로 전송합니다.

------------------------------------------------
5) 함수별 역할 (간단)
- send_rrq(filename, mode)
  → RRQ 패킷 만들어서 server_address로 전송

- send_wrq(filename, mode)
  → WRQ 패킷 만들어서 server_address로 전송

- send_ack(block_num, server)
  → ACK 패킷 만들어서 server(주소/포트)로 전송

------------------------------------------------
6) GET(다운로드) 동작 방식: tftp_get()
(1) RRQ 전송
- send_rrq()로 “파일 주세요” 요청을 먼저 보냅니다.

(2) 로컬 파일 열기
- open(filename, "wb")로 같은 이름의 파일을 새로 씁니다(덮어씀).

(3) DATA를 블록 단위로 받기 (512바이트 단위)
- expected_block_number = 1부터 시작합니다.
- 서버가 보내는 DATA를 recvfrom()으로 받습니다.

(4) 서버 포트(중요)
- TFTP는 처음 RRQ/WRQ는 보통 69번 포트로 보내지만,
  서버는 실제 전송(DATA/ACK)은 “새로운 임시 포트”에서 보내는 경우가 많습니다.
- 그래서 코드는 첫 응답의 addr(주소/포트)를 server_new_addr로 저장하고,
  이후 ACK는 그 주소로 보냅니다.

(5) 정상 블록이면 파일에 쓰고 ACK 보내기
- block_number == expected_block_number 인 경우:
  - 파일에 write()
  - ACK(block_number) 보내기
  - expected_block_number += 1

(6) 마지막 블록이면 종료
- DATA의 실제 payload 길이가 512보다 작으면 마지막 블록입니다.
  → 다운로드 완료로 판단하고 loop 종료

(7) ERROR 처리
- 서버가 ERROR를 보내면 errorcode를 읽어 메시지 출력 후 종료합니다.

(8) 타임아웃 처리
- recvfrom()이 timeout되면 “서버 응답이 없습니다” 출력하고 종료합니다.

------------------------------------------------
7) PUT(업로드) 동작 방식: tftp_put()
(1) 로컬 파일 존재 확인
- os.path.exists(filename)로 파일이 없으면 업로드 불가 → 종료

(2) WRQ 전송
- send_wrq()로 “파일 업로드할게요” 요청을 보냅니다.

(3) 서버의 ACK(블록 0) 또는 ERROR 기다리기
- 정상이라면 서버가 ACK(0)을 보냅니다.
  - opcode가 ERROR면 에러 출력 후 종료
  - opcode가 ACK가 아니면 이상 상황으로 종료
  - ACK 블록 번호가 0이 아니면 이상 상황으로 종료

(4) 서버 포트(중요)
- GET과 동일하게, 이후 DATA/ACK는 server_new_addr(새 포트)로 통신합니다.

(5) 파일을 512바이트씩 읽어서 DATA 전송
- block_num = 1부터 시작
- chunk = f.read(512)
- DATA 패킷 구성: [DATA opcode][block_num][chunk]
- sendto()로 전송

(6) ACK 확인
- ACK를 받으면 ack_block == block_num인지 확인합니다.
- 맞으면 다음 블록으로 진행합니다.

(7) 마지막 블록이면 종료
- 마지막 chunk 크기가 512보다 작으면 마지막 전송입니다.
  → “업로드 완료” 출력 후 종료

(8) 타임아웃 처리
- ACK 대기 중 timeout이면 “ACK 대기 중 타임아웃” 출력 후 종료

------------------------------------------------
8) 이 코드의 특징/주의점 (한 줄 요약)
- UDP 기반 TFTP로 RRQ/WRQ → DATA/ACK를 블록 단위(512B)로 주고받습니다.
- 서버는 실제 전송을 새 포트로 진행할 수 있어 첫 응답 주소(addr)를 계속 사용합니다.
- 타임아웃 처리가 들어가 있어 서버가 응답 없으면 종료합니다.
- get은 로컬 파일을 같은 이름으로 “덮어쓰기” 합니다.

