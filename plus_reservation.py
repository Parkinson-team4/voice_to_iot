import asyncio
import os
import speech_recognition as sr
import json
import aiohttp
import pyttsx3
from dotenv import load_dotenv
import schedule
import threading
import time
from datetime import datetime, timedelta
import re
import pvporcupine
import pyaudio
import struct
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
print("🔍 Azure Function URL:", os.getenv("AZURE_FUNCTION_URL"))
print("🔍 디바이스 ID:", os.getenv("DEVICE_ID"))
print("🔍 Porcupine Access Key:", "설정됨" if os.getenv("PORCUPINE_ACCESS_KEY") else "❌ 설정 필요")

# 예약 정보 저장용 전역 변수
scheduled_jobs = []
scheduler_running = False


def speak_text(text):
    """TTS 설정 최적화"""
    print(f"🔊 bumblebee: {text}")
    try:
        tts_engine = pyttsx3.init()
        
        # TTS 속도와 음성 설정
        voices = tts_engine.getProperty('voices')
        if voices:
            # 한국어 또는 여성 음성 선택
            for voice in voices:
                if 'korean' in voice.name.lower() or 'female' in voice.name.lower():
                    tts_engine.setProperty('voice', voice.id)
                    break
        
        tts_engine.setProperty('rate', 180)  # 말하기 속도 (기본: 200)
        tts_engine.setProperty('volume', 0.9)  # 볼륨
        
        tts_engine.say(text)
        tts_engine.runAndWait()
        
    except Exception as e:
        print(f"❌ TTS 오류: {e}")


class PorcupineWakeWordDetector:
    """Porcupine 웨이크 워드 감지기"""
    
    def __init__(self, access_key, keywords=None):
        self.access_key = access_key
        self.keywords = keywords or ['bumblebee']  # 기본 키워드
        self.porcupine = None
        self.pa = None
        self.audio_stream = None
        
    def initialize(self):
        """Porcupine 초기화"""
        try:
            # Porcupine 객체 생성
            self.porcupine = pvporcupine.create(
                access_key=self.access_key,
                keywords=self.keywords,
                sensitivities=[0.7] * len(self.keywords)  # 민감도 설정
            )
            
            # PyAudio 초기화
            self.pa = pyaudio.PyAudio()
            
            # 오디오 스트림 설정
            self.audio_stream = self.pa.open(
                rate=self.porcupine.sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=self.porcupine.frame_length
            )
            
            print(f"✅ Porcupine 초기화 완료 - 키워드: {self.keywords}")
            print(f"   샘플레이트: {self.porcupine.sample_rate}Hz")
            print(f"   프레임 길이: {self.porcupine.frame_length}")
            
            return True
            
        except Exception as e:
            print(f"❌ Porcupine 초기화 실패: {e}")
            return False
    
    def listen_for_wake_word(self, timeout=None):
        """웨이크 워드 감지"""
        if not self.porcupine or not self.audio_stream:
            print("❌ Porcupine가 초기화되지 않았습니다.")
            return False
        
        print("🎤 웨이크 워드 감지 중...")
        start_time = time.time()
        
        try:
            while True:
                # 타임아웃 체크
                if timeout and (time.time() - start_time) > timeout:
                    return False
                
                # 오디오 데이터 읽기
                pcm = self.audio_stream.read(self.porcupine.frame_length)
                pcm = struct.unpack_from("h" * self.porcupine.frame_length, pcm)
                
                # 웨이크 워드 감지
                keyword_index = self.porcupine.process(pcm)
                
                if keyword_index >= 0:
                    detected_keyword = self.keywords[keyword_index]
                    print(f"✅ 웨이크 워드 감지됨: '{detected_keyword}'")
                    return True
                    
        except Exception as e:
            print(f"❌ 웨이크 워드 감지 오류: {e}")
            return False
    
    def cleanup(self):
        """리소스 정리"""
        try:
            if self.audio_stream:
                self.audio_stream.close()
            if self.pa:
                self.pa.terminate()
            if self.porcupine:
                self.porcupine.delete()
            print("✅ Porcupine 리소스 정리 완료")
        except Exception as e:
            print(f"❌ Porcupine 정리 오류: {e}")


def setup_speech_recognizer():
    """음성 인식기 설정"""
    recognizer = sr.Recognizer()
    
    try:
        microphone = sr.Microphone()
        
        with microphone as source:
            print("🔧 음성 인식기 캘리브레이션 중...")
            recognizer.adjust_for_ambient_noise(source, duration=1)
            
        # 인식 파라미터 최적화
        recognizer.energy_threshold = 300
        recognizer.dynamic_energy_threshold = True
        recognizer.pause_threshold = 0.8
        recognizer.operation_timeout = 1
        
        print("✅ 음성 인식기 설정 완료")
        return recognizer, microphone
        
    except Exception as e:
        print(f"❌ 음성 인식기 설정 오류: {e}")
        return None, None


def recognize_speech_improved(recognizer, microphone, timeout=10, phrase_limit=5):
    """개선된 음성 인식 함수"""
    try:
        print("🎤 명령어 음성 입력 대기 중...")
        
        with microphone as source:
            # 실시간 잡음 조정
            recognizer.adjust_for_ambient_noise(source, duration=0.3)
            
            print(f"✅ 명령어를 말씀해 주세요 (최대 {phrase_limit}초)")
            
            # 오디오 캡처
            audio = recognizer.listen(
                source, 
                timeout=timeout,
                phrase_time_limit=phrase_limit
            )
            
        print("🔄 음성 인식 중...")
        
        # 여러 언어로 시도
        languages_to_try = ["ko-KR", "en-US"]
        
        for lang in languages_to_try:
            try:
                print(f"🌐 {lang} 언어로 인식 시도...")
                text = recognizer.recognize_google(audio, language=lang)
                print(f"✅ 인식 성공 ({lang}): '{text}'")
                return text
                
            except sr.UnknownValueError:
                continue
            except sr.RequestError as e:
                print(f"❌ {lang} API 오류: {e}")
                continue
        
        print("❌ 모든 언어로 음성 인식 실패")
        return None
        
    except sr.WaitTimeoutError:
        print(f"❌ {timeout}초 동안 음성이 감지되지 않았습니다.")
        return None
    except Exception as e:
        print(f"❌ 음성 인식 오류: {e}")
        return None


async def send_command_to_azure_function(command):
    """Azure Function에 HTTP 요청을 보내서 IoT Hub로 메시지를 전달합니다."""
    try:
        function_url = os.getenv("AZURE_FUNCTION_URL")

        if not function_url:
            raise ValueError("AZURE_FUNCTION_URL 환경 변수가 설정되지 않았습니다.")

        payload = {
            "command": command,
            "deviceId": os.getenv("DEVICE_ID", "default-device"),
            "timestamp": time.time(),
        }

        print(f"🌐 Azure Function으로 요청 전송: {function_url}")
        print(f"📄 요청 데이터: {json.dumps(payload, indent=2)}")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                function_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
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


def execute_scheduled_command(command, job_id):
    """예약된 명령어 실행"""
    print(f"⏰ 예약된 명령어 실행: {command}")

    if command == "turn on the light":
        speak_text("예약된 시간이 되었습니다. 조명을 켜겠습니다.")
    elif command == "turn off the light":
        speak_text("예약된 시간이 되었습니다. 조명을 끄겠습니다.")

    # 비동기 함수를 동기적으로 실행
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(send_command_to_azure_function(command))
    finally:
        loop.close()

    # 실행된 예약 제거
    global scheduled_jobs
    scheduled_jobs = [job for job in scheduled_jobs if job["id"] != job_id]
    print(f"✅ 예약 작업 완료 및 제거 (ID: {job_id})")


def parse_time_expression(text):
    """시간 표현을 파싱하여 실행 시간 계산"""
    original_text = text
    text = text.replace(" ", "")

    # 날짜 표현 파싱
    date_offset = 0
    date_keywords = {
        "오늘": 0, "내일": 1, "모레": 2, "다음날": 1,
        "tomorrow": 1, "today": 0,
    }

    for keyword, offset in date_keywords.items():
        if keyword in original_text.lower():
            date_offset = offset
            print(f"🗓️ 날짜 키워드 발견: '{keyword}' → {offset}일 후")
            break

    # 분 단위 패턴
    minute_pattern = r"(\d+)분[후뒤]"
    minute_match = re.search(minute_pattern, text)
    if minute_match:
        minutes = int(minute_match.group(1))
        target_time = datetime.now() + timedelta(minutes=minutes)
        return target_time, f"{minutes}분 후"

    # 시간 단위 패턴
    hour_pattern = r"(\d+)시간[후뒤]"
    hour_match = re.search(hour_pattern, text)
    if hour_match:
        hours = int(hour_match.group(1))
        target_time = datetime.now() + timedelta(hours=hours)
        return target_time, f"{hours}시간 후"

    # 초 단위 패턴 (테스트용)
    second_pattern = r"(\d+)초[후뒤]"
    second_match = re.search(second_pattern, text)
    if second_match:
        seconds = int(second_match.group(1))
        target_time = datetime.now() + timedelta(seconds=seconds)
        return target_time, f"{seconds}초 후"

    # 구체적 시간 패턴
    time_patterns = [
        (r"오후(\d+)시(\d+)분", lambda h, m: (int(h) + 12 if int(h) != 12 else 12, int(m))),
        (r"저녁(\d+)시(\d+)분", lambda h, m: (int(h) + 12 if int(h) < 12 else int(h), int(m))),
        (r"밤(\d+)시(\d+)분", lambda h, m: (int(h) + 12 if int(h) < 12 else int(h), int(m))),
        (r"오전(\d+)시(\d+)분", lambda h, m: (int(h) if int(h) != 12 else 0, int(m))),
        (r"새벽(\d+)시(\d+)분", lambda h, m: (int(h), int(m))),
        (r"(\d+)시(\d+)분", lambda h, m: (int(h), int(m))),
        (r"오후(\d+)시", lambda h: (int(h) + 12 if int(h) != 12 else 12, 0)),
        (r"저녁(\d+)시", lambda h: (int(h) + 12 if int(h) < 12 else int(h), 0)),
        (r"밤(\d+)시", lambda h: (int(h) + 12 if int(h) < 12 else int(h), 0)),
        (r"오전(\d+)시", lambda h: (int(h) if int(h) != 12 else 0, 0)),
        (r"새벽(\d+)시", lambda h: (int(h), 0)),
        (r"(\d+)시", lambda h: (int(h), 0)),
    ]

    for pattern, time_converter in time_patterns:
        match = re.search(pattern, text)
        if match:
            groups = match.groups()
            if len(groups) == 2:
                hour, minute = time_converter(groups[0], groups[1])
            else:
                hour, minute = time_converter(groups[0])

            now = datetime.now()
            target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            if date_offset > 0:
                target_time += timedelta(days=date_offset)
                time_desc = f"{'내일' if date_offset == 1 else '모레'} {target_time.strftime('%H:%M')}"
            else:
                if target_time <= now:
                    target_time += timedelta(days=1)
                    time_desc = f"내일 {target_time.strftime('%H:%M')}"
                else:
                    time_desc = f"오늘 {target_time.strftime('%H:%M')}"

            return target_time, time_desc

    return None, None


def analyze_command_with_schedule(text):
    """명령어 분석 (예약 기능 포함)"""
    if not text:
        return None, None, None

    text_lower = text.lower()
    print(f"🔍 명령어 분석 중: '{text}'")

    # 예약 취소 명령
    cancel_keywords = ["취소", "삭제", "없애", "그만", "cancel", "stop"]
    schedule_keywords = ["예약", "스케줄", "schedule"]

    if any(k in text_lower for k in cancel_keywords) and any(k in text_lower for k in schedule_keywords):
        return "cancel_schedule", None, None

    # 예약 확인 명령
    check_keywords = ["확인", "보기", "알려줘", "뭐가", "어떤", "list", "show"]
    if any(k in text_lower for k in check_keywords) and any(k in text_lower for k in schedule_keywords):
        return "check_schedule", None, None

    # 시간 표현 파싱
    target_time, time_desc = parse_time_expression(text)

    # 조명 제어 키워드 (더 많은 변형)
    turn_on_keywords = ["켜", "키", "on", "온", "점등", "불켜", "라이트켜"]
    turn_off_keywords = ["꺼", "끄", "off", "오프", "소등", "불꺼", "라이트꺼"]
    light_keywords = ["불", "라이트", "light", "조명", "전등", "등", "램프"]

    has_light_keyword = any(k in text_lower for k in light_keywords)
    has_turn_on = any(k in text_lower for k in turn_on_keywords)
    has_turn_off = any(k in text_lower for k in turn_off_keywords)

    print(f"  조명 키워드: {has_light_keyword}, 켜기: {has_turn_on}, 끄기: {has_turn_off}")

    # 조명 명령어 결정
    command = None
    if has_turn_on and not has_turn_off:
        command = "turn on the light"
    elif has_turn_off and not has_turn_on:
        command = "turn off the light"
    elif has_light_keyword and has_turn_on:
        command = "turn on the light"
    elif has_light_keyword and has_turn_off:
        command = "turn off the light"
    elif has_light_keyword and not has_turn_off:
        print("  조명 키워드만 감지됨 → 켜기로 추정")
        command = "turn on the light"

    print(f"  최종 명령: {command}")
    return command, target_time, time_desc


def add_scheduled_job(command, target_time, time_desc):
    """예약 작업 추가"""
    job_id = f"job_{int(time.time())}"

    now = datetime.now()
    if target_time <= now + timedelta(minutes=1):
        delay_seconds = (target_time - now).total_seconds()
        if delay_seconds > 0:
            def delayed_execution():
                time.sleep(delay_seconds)
                execute_scheduled_command(command, job_id)

            thread = threading.Thread(target=delayed_execution, daemon=True)
            thread.start()

            job_info = {
                "id": job_id,
                "command": command,
                "time": target_time.strftime("%Y-%m-%d %H:%M:%S"),
                "description": time_desc,
                "job_object": None,
            }
            scheduled_jobs.append(job_info)
        else:
            speak_text("죄송합니다. 이미 지난 시간입니다.")
            return
    else:
        job = (
            schedule.every()
            .day.at(target_time.strftime("%H:%M"))
            .do(execute_scheduled_command, command, job_id)
            .tag(job_id)
        )

        job_info = {
            "id": job_id,
            "command": command,
            "time": target_time.strftime("%Y-%m-%d %H:%M"),
            "description": time_desc,
            "job_object": job,
        }
        scheduled_jobs.append(job_info)

    action = "조명을 켜는" if command == "turn on the light" else "조명을 끄는"
    speak_text(f"네, {time_desc}에 {action} 작업을 예약하겠습니다.")
    print(f"✅ 예약 등록: {action} 작업 - {target_time.strftime('%Y-%m-%d %H:%M:%S')}")


def cancel_all_schedules():
    """모든 예약 취소"""
    global scheduled_jobs

    if not scheduled_jobs:
        speak_text("현재 취소할 예약이 없습니다.")
        return

    for job_info in scheduled_jobs:
        if job_info["job_object"]:
            schedule.cancel_job(job_info["job_object"])

    count = len(scheduled_jobs)
    scheduled_jobs = []
    speak_text(f"네, 총 {count}개의 예약을 모두 취소했습니다.")
    print(f"✅ {count}개 예약 취소 완료")


def show_schedules():
    """현재 예약 목록 보기"""
    if not scheduled_jobs:
        speak_text("현재 예약된 작업이 없습니다.")
        return

    speak_text(f"현재 {len(scheduled_jobs)}개의 예약이 있습니다.")
    print("\n📅 현재 예약 목록:")

    for i, job_info in enumerate(scheduled_jobs, 1):
        action = "조명 켜기" if job_info["command"] == "turn on the light" else "조명 끄기"
        print(f"  {i}. {action} - {job_info['time']}")
        if i == 1:
            speak_text(f"첫 번째로 {job_info['description']}에 {action} 예약이 있습니다.")


def run_scheduler():
    """백그라운드 스케줄러 실행"""
    global scheduler_running
    scheduler_running = True
    print("📅 스케줄러 시작됨")

    while scheduler_running:
        schedule.run_pending()
        time.sleep(1)


async def main():
    print("🎯 bumblebee 음성 제어 시스템 시작 (Porcupine 웨이크 워드 감지)")
    
    # 필수 환경 변수 확인
    access_key = os.getenv("PORCUPINE_ACCESS_KEY")
    if not access_key:
        print("❌ PORCUPINE_ACCESS_KEY 환경 변수가 설정되지 않았습니다.")
        print("   Picovoice Console (https://console.picovoice.ai)에서 무료 액세스 키를 받아주세요.")
        return
    
    # 웨이크 워드 감지기 초기화
    wake_detector = PorcupineWakeWordDetector(
        access_key=access_key,
        keywords=['bumblebee']  # 기본 제공 키워드
    )
    
    if not wake_detector.initialize():
        print("❌ Porcupine 초기화 실패")
        return
    
    # 음성 인식기 설정
    recognizer, microphone = setup_speech_recognizer()
    if not recognizer or not microphone:
        print("❌ 음성 인식기 초기화 실패")
        wake_detector.cleanup()
        return

    # 스케줄러 백그라운드 시작
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    print("🎙️ 'bumblebee' 이라고 말해주세요 → 조명 명령 또는 예약 대기")

    try:
        while True:
            print(f"\n📣 웨이크 워드 대기 중... (현재 예약: {len(scheduled_jobs)}개)")
            
            # Porcupine으로 웨이크 워드 감지
            if wake_detector.listen_for_wake_word():
                speak_text("네, 무엇을 도와드릴까요?")
                
                print("\n💡 명령을 말해주세요!")
                print("  즉시 실행: '불 켜줘', '불 꺼줘'")
                print("  예약: '10분 후에 불 켜줘', '오늘 오후 7시에 불 꺼줘'")
                print("  관리: '예약 확인해줘', '예약 취소해줘'")
                
                # 명령어 인식
                for attempt in range(3):
                    print(f"\n🗣️ 명령 인식 시도 {attempt + 1}/3")
                    
                    recognized_text = recognize_speech_improved(
                        recognizer, microphone,
                        timeout=15, phrase_limit=8
                    )

                    if recognized_text:
                        command, target_time, time_desc = analyze_command_with_schedule(recognized_text)

                        if command == "cancel_schedule":
                            cancel_all_schedules()
                            break
                        elif command == "check_schedule":
                            show_schedules()
                            break
                        elif command and target_time:
                            add_scheduled_job(command, target_time, time_desc)
                            break
                        elif command:
                            if command == "turn on the light":
                                speak_text("네, 조명을 켜겠습니다.")
                            elif command == "turn off the light":
                                speak_text("네, 조명을 끄겠습니다.")

                            action_text = "조명 켜기" if command == "turn on the light" else "조명 끄기"
                            print(f"✅ {action_text} 명령이 인식되었습니다!")
                            await send_command_to_azure_function(command)
                            break
                        else:
                            speak_text("죄송합니다. 명령을 이해하지 못했습니다. 다시 말씀해 주세요.")
                            print(f"❌ 인식할 수 없는 명령입니다. 인식된 텍스트: '{recognized_text}'")
                    else:
                        speak_text("음성을 인식하지 못했습니다. 다시 말씀해 주세요.")
                        print("❌ 음성 인식 실패. 다시 시도해주세요.")

                    if attempt < 2:
                        print("⏳ 1초 후 다시 시도합니다...")
                        await asyncio.sleep(1)
                else:
                    speak_text("죄송합니다. 명령을 인식하지 못했습니다. 다시 웨이크 워드를 말해주세요.")
                    print("❌ 3번 시도 후에도 명령을 인식하지 못했습니다.")

                print("\n🔄 명령 처리 완료. 웨이크 워드를 기다립니다...")
                await asyncio.sleep(1)
            
            await asyncio.sleep(0.1)  # CPU 부하 줄이기
            
    except KeyboardInterrupt:
        print("\n👋 프로그램을 종료합니다.")
    finally:
        wake_detector.cleanup()
        global scheduler_running
        scheduler_running = False


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 프로그램을 종료합니다.")
        scheduler_running = False