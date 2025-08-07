import asyncio
import os
import speech_recognition as sr
import json
import aiohttp
import pyttsx3
from dotenv import load_dotenv

load_dotenv()
print("🔍 Azure Function URL:", os.getenv("AZURE_FUNCTION_URL"))
print("🔍 디바이스 ID:", os.getenv("DEVICE_ID"))


def speak_text(text):
    print(text)
    # TTS 엔진 초기화
    tts_engine = pyttsx3.init()
    tts_engine.say(text)
    tts_engine.runAndWait()

async def send_command_to_azure_function(command):
    """
    Azure Function에 HTTP 요청을 보내서 IoT Hub로 메시지를 전달합니다.
    """
    try:
        function_url = os.getenv("AZURE_FUNCTION_URL")
        
        if not function_url:
            raise ValueError("AZURE_FUNCTION_URL 환경 변수가 설정되지 않았습니다.")
            
        payload = {
            "command": command,
            "deviceId": os.getenv("DEVICE_ID", "default-device"),
            "timestamp": asyncio.get_event_loop().time()
        }
        
        print(f"🌐 Azure Function으로 요청 전송: {function_url}")
        print(f"📄 요청 데이터: {json.dumps(payload, indent=2)}")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                function_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                
                status_code = response.status
                response_text = await response.text()
                
                print(f"📊 응답 상태 코드: {status_code}")
                print(f"📨 응답 내용: {response_text}")
                
                if status_code == 200:
                    print("✅ Azure Function 요청 성공!")
                    try:
                        response_json = json.loads(response_text)
                        if response_json.get("success"):
                            print("✅ IoT Hub 메시지 전송 완료!")
                        else:
                            print(f"❌ IoT Hub 전송 실패: {response_json.get('error', '알 수 없는 오류')}")
                    except json.JSONDecodeError:
                        print("✅ 응답을 텍스트로 받았습니다.")
                else:
                    print(f"❌ Azure Function 요청 실패 (상태 코드: {status_code})")
                    
    except aiohttp.ClientTimeout:
        print("❌ Azure Function 요청 시간 초과 (10초)")
    except aiohttp.ClientError as e:
        print(f"❌ HTTP 요청 오류: {e}")
    except Exception as e:
        print(f"❌ Azure Function 요청 오류: {e}")

def analyze_command(text):
    if not text:
        return None
    
    text_lower = text.lower()
    
    turn_on_keywords = ["켜", "키", "on", "온"]
    turn_off_keywords = ["꺼", "끄", "off", "오프"]
    light_keywords = ["불", "라이트", "light", "조명", "전등"]
    
    has_light_keyword = any(k in text_lower for k in light_keywords)
    has_turn_on = any(k in text_lower for k in turn_on_keywords)
    has_turn_off = any(k in text_lower for k in turn_off_keywords)
    
    if has_turn_on and not has_turn_off:
        return "turn on the light"
    elif has_turn_off and not has_turn_on:
        return "turn off the light"
    elif has_light_keyword and has_turn_on:
        return "turn on the light"
    elif has_light_keyword and has_turn_off:
        return "turn off the light"
    else:
        return None

def recognize_speech_from_mic():
    recognizer = sr.Recognizer()
    
    print("🎤 사용 가능한 마이크:")
    for i, name in enumerate(sr.Microphone.list_microphone_names()):
        print(f"  {i}: {name}")
    
    try:
        with sr.Microphone() as source:
            print("\n🔧 마이크 설정 중... (주변 소음 측정 0.5초)")
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            recognizer.energy_threshold = 4000
            recognizer.dynamic_energy_threshold = True
            recognizer.pause_threshold = 1
            
            print("✅ 준비 완료! 명령을 말해주세요 (최대 3초간 녹음)")
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=3)
            print("🔄 음성 인식 중...")

    except sr.WaitTimeoutError:
        print("❌ 음성 입력 시간이 초과되었습니다.")
        return None
    except Exception as e:
        print(f"❌ 마이크 오류: {e}")
        return None

    try:
        print("🌐 Google 음성 인식 시도 중...")
        text = recognizer.recognize_google(audio, language='ko-KR')
        print(f"✅ 인식된 음성: '{text}'")
        return text
    except sr.UnknownValueError:
        print("❌ 음성을 인식할 수 없습니다.")
        return None
    except sr.RequestError as e:
        print(f"❌ Google Speech Recognition API 오류: {e}")
        print("💡 인터넷 연결을 확인해주세요.")
        return None

async def main():
    print("🎯 음성 제어 시스템 시작")
    print("🎙️ 호출어: '새싹' → 조명 명령 대기")

    recognizer = sr.Recognizer()

    for attempt in range(3):
        print(f"\n📣 호출 대기 중... (시도 {attempt + 1}/3)")

        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                print("🟢 '새싹' 이라고 불러주세요.")
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=2)
                trigger_text = recognizer.recognize_google(audio, language="ko-KR")
                print(f"👂 인식된 텍스트: {trigger_text}")

                if "새싹" in trigger_text:
                    speak_text("네, 새싹이에요. 말씀하세요!")
                    break
                else:
                    print("❌ 호출어가 아닙니다. 다시 시도해주세요.")

        except sr.WaitTimeoutError:
            print("⏱ 음성이 감지되지 않았습니다. 다시 시도해주세요.")
        except sr.UnknownValueError:
            print("❌ 음성을 인식할 수 없습니다. 다시 시도해주세요.")
        except sr.RequestError as e:
            print(f"⚠️ 음성 인식 오류: {e}")
            return

        if attempt < 2:
            await asyncio.sleep(1)
    else:
        print("❌ '새싹'이 호출이 인식되지 않았습니다. 프로그램을 종료합니다.")
        return

    print("\n💡 조명 제어 명령을 말해주세요!")
    print("  🔆 불 켜기 예: 불 켜줘, 켜, 라이트 온")
    print("  🔅 불 끄기 예: 불 꺼줘, 꺼, 라이트 오프")

    for attempt in range(3):
        print(f"\n🗣️ 명령 인식 시도 {attempt + 1}/3")
        recognized_text = recognize_speech_from_mic()

        if recognized_text:
            standardized_command = analyze_command(recognized_text)

            if standardized_command:
                if standardized_command == "turn on the light":
                    speak_text("불을 켭니다.")
                elif standardized_command == "turn off the light":
                    speak_text("불을 끕니다.")

                action_text = "조명 켜기" if standardized_command == "turn on the light" else "조명 끄기"
                print(f"✅ {action_text} 명령이 인식되었습니다!")
                await send_command_to_azure_function(standardized_command)
                break
            else:
                print(f"❌ 조명 제어 명령이 아닙니다. 인식된 텍스트: '{recognized_text}'")
        else:
            print("❌ 음성 인식 실패. 다시 시도해주세요.")

        if attempt < 2:
            print("⏳ 1초 후 다시 시도합니다...")
            await asyncio.sleep(1)
    else:
        print("❌ 3번 시도 후에도 명령을 인식하지 못했습니다.")

if __name__ == "__main__":
    asyncio.run(main())