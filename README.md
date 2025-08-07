# 📡 Voice-to-IoT 시스템

## 📌 소개

이 프로젝트는 사용자의 **텍스트 명령** 또는 **음성 인식 결과**를 바탕으로, 클라우드를 통해 원격 IoT 디바이스를 제어하는 시스템입니다.  
특히 **Azure Functions**와 **Azure IoT Hub**를 활용하여, 서버리스 환경에서도 실시간 디바이스 제어가 가능하도록 구성했습니다.

예시 명령:

- "불 켜" → 조명 On
- "불 꺼" → 조명 Off

---

## 🔧 시스템 아키텍처

이 시스템은 다음과 같은 구조로 구성되어 있습니다:
<pre>
[사용자 입력 (텍스트)]
│
▼
[Python 앱 (txt_azurefunction.py)]
│ └─ 텍스트 → 명령 파싱
▼
[Azure Function (HTTP Trigger)]
│ └─ 인증 후 명령 전달
▼
[Azure IoT Hub]
│ └─ IoT 디바이스로 메시지 전송
▼
[IoT 디바이스 (조명)]
└─ 명령 수신 → 제어 수행
</pre>

## 🧩 기술 스택

- Python 3.x
- Azure Functions (HTTP Trigger)
- Azure IoT Hub
- IoT 디바이스 (예: Raspberry Pi, ESP32 등)
