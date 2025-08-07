import asyncio
import os
import json
import aiohttp
from dotenv import load_dotenv

load_dotenv()
print("🔍 Azure Function URL:", os.getenv("AZURE_FUNCTION_URL"))
print("🔍 디바이스 ID:", os.getenv("DEVICE_ID"))

async def send_command_to_azure_function(command):
    """
    Azure Function에 HTTP 요청을 보내서 IoT Hub로 메시지를 전달합니다.
    """
    try:
        function_url = os.getenv("AZURE_FUNCTION_URL")
        
        if not function_url:
            raise ValueError("AZURE_FUNCTION_URL 환경 변수가 설정되지 않았습니다.")
            
        # 요청 데이터 준비
        payload = {
            "command": command,
            "deviceId": os.getenv("DEVICE_ID", "default-device"),
            "timestamp": asyncio.get_event_loop().time()
        }
        
        print(f"🌐 Azure Function으로 요청 전송: {function_url}")
        print(f"📄 요청 데이터: {json.dumps(payload, indent=2)}")
        
        # HTTP 요청 전송
        async with aiohttp.ClientSession() as session:
            async with session.post(
                function_url,
                json=payload,
                headers={
                    "Content-Type": "application/json"
                },
                timeout=aiohttp.ClientTimeout(total=30)
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
        print("❌ Azure Function 요청 시간 초과 (30초)")
    except aiohttp.ClientError as e:
        print(f"❌ HTTP 요청 오류: {e}")
    except Exception as e:
        print(f"❌ Azure Function 요청 오류: {e}")


def analyze_command(text):
    """
    입력된 텍스트를 분석하여 조명 제어 명령인지 판단하고
    'turn on the light' 또는 'turn off the light'로 변환합니다.
    """
    if not text:
        return None
    
    # 텍스트를 소문자로 변환하여 대소문자 구분 없이 처리
    text_lower = text.lower()
    
    # 불 켜기 관련 키워드들
    turn_on_keywords = [
        "켜", "키", "on", "온"
    ]
    
    # 불 끄기 관련 키워드들  
    turn_off_keywords = [
        "꺼", "끄", "off", "오프"
    ]
    
    # 조명 관련 키워드들
    light_keywords = [
        "불", "라이트", "light", "조명", "전등"
    ]
    
    # 조명 관련 키워드가 포함되어 있는지 확인
    has_light_keyword = any(keyword in text_lower for keyword in light_keywords)
    
    # 조명 키워드가 없더라도 켜기/끄기 키워드만으로도 판단 (간단한 명령)
    has_turn_on = any(keyword in text_lower for keyword in turn_on_keywords)
    has_turn_off = any(keyword in text_lower for keyword in turn_off_keywords)
    
    # 표준화된 명령어로 변환
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


def get_text_input():
    """
    사용자로부터 텍스트 입력을 받습니다.
    """
    try:
        print("💬 조명 제어 명령을 입력하세요:")
        text = input(">>> ").strip()
        
        if text:
            print(f"✅ 입력된 텍스트: '{text}'")
            return text
        else:
            print("❌ 빈 텍스트입니다. 다시 입력해주세요.")
            return None
            
    except KeyboardInterrupt:
        print("\n❌ 사용자가 중단했습니다.")
        return None
    except Exception as e:
        print(f"❌ 입력 오류: {e}")
        return None


async def main():
    """
    메인 실행 함수 - 텍스트 입력 및 Azure Function 요청
    """
    print("🎯 Azure Function을 통한 텍스트 조명 제어 시작!")
    print("지원되는 명령어:")
    print("  🔆 불 켜기: 불켜줘, 불 좀 켜, 켜, 라이트온, turn on")
    print("  🔅 불 끄기: 불꺼줘, 불 좀 꺼, 꺼, 라이트오프, turn off")
    print("  💡 키워드 기반으로 자연스러운 표현이 가능합니다!")
    print("  🌐 Azure Function → IoT Hub 경로로 메시지가 전송됩니다.")
    print()
    
    # 최대 3번 시도
    for attempt in range(3):
        print(f"🔄 시도 {attempt + 1}/3")
        user_input = get_text_input()
        
        if user_input:
            # 키워드 기반 분석으로 표준화된 명령어 생성
            standardized_command = analyze_command(user_input)
            
            if standardized_command:
                action_text = "조명 켜기" if standardized_command == "turn on the light" else "조명 끄기"
                print(f"✅ {action_text} 명령이 인식되었습니다!")
                print(f"📡 Azure Function으로 전송할 명령: '{standardized_command}'")
                await send_command_to_azure_function(standardized_command)
                print("🎯 명령 처리가 완료되었습니다. 프로그램을 종료합니다.")
                break
            else:
                print(f"❌ 조명 제어 명령이 아닙니다. 입력된 텍스트: '{user_input}'")
                print("💡 '불 켜줘', '라이트 온', 'turn on' 등으로 시도해주세요.")
        else:
            print("❌ 텍스트 입력 실패. 다시 시도해주세요.")
            
        if attempt < 2:  # 마지막 시도가 아니면
            print("⏳ 잠시 후 다시 시도합니다...")
            await asyncio.sleep(1)
    
    else:
        print("❌ 3번 시도 후에도 명령을 인식하지 못했습니다.")
        print("👋 프로그램을 종료합니다.")
    
    print("🏁 프로그램이 종료되었습니다.")


if __name__ == "__main__":
    asyncio.run(main())