import azure.functions as func
import json
import logging
import os
import asyncio
from azure.iot.hub import IoTHubRegistryManager
from azure.iot.device.aio import IoTHubDeviceClient

app = func.FunctionApp()

def analyze_command(text):
    """
    텍스트를 분석하여 조명 제어 명령인지 판단합니다.
    """
    if not text:
        return None
    
    text_lower = text.lower()
    
    # 불 켜기 관련 키워드들
    turn_on_keywords = ["turn on the light", "켜", "키", "on", "온"]
    
    # 불 끄기 관련 키워드들  
    turn_off_keywords = ["turn off the light", "꺼", "끄", "off", "오프"]
    
    # 조명 관련 키워드들
    light_keywords = ["불", "라이트", "light", "조명", "전등"]
    
    has_light_keyword = any(keyword in text_lower for keyword in light_keywords)
    has_turn_on = any(keyword in text_lower for keyword in turn_on_keywords)
    has_turn_off = any(keyword in text_lower for keyword in turn_off_keywords)
    
    if "turn on the light" in text_lower or (has_turn_on and not has_turn_off):
        return "turn_on"
    elif "turn off the light" in text_lower or (has_turn_off and not has_turn_on):
        return "turn_off"
    elif has_light_keyword and has_turn_on:
        return "turn_on"
    elif has_light_keyword and has_turn_off:
        return "turn_off"
    else:
        return None

@app.function_name(name="SendIoTCommand")
@app.route(route="send-command", methods=["POST"])
def send_iot_command(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP 요청을 받아서 IoT Hub로 C2D 메시지를 전송하는 Azure Function
    """
    logging.info('SendIoTCommand HTTP trigger function processed a request.')
    
    try:
        # 요청 본문에서 JSON 데이터 파싱
        try:
            req_body = req.get_json()
            if not req_body:
                return func.HttpResponse(
                    json.dumps({"success": False, "error": "요청 본문이 비어있습니다."}, ensure_ascii=False),
                    status_code=400,
                    headers={"Content-Type": "application/json; charset=utf-8"}
                )
        except ValueError as e:
            return func.HttpResponse(
                json.dumps({"success": False, "error": f"JSON 파싱 오류: {str(e)}"}, ensure_ascii=False),
                status_code=400,
                headers={"Content-Type": "application/json; charset=utf-8"}
            )
        
        # 필수 파라미터 확인
        command = req_body.get('command')
        device_id = req_body.get('deviceId')
        
        if not command:
            return func.HttpResponse(
                json.dumps({"success": False, "error": "command 파라미터가 필요합니다."}, ensure_ascii=False),
                status_code=400,
                headers={"Content-Type": "application/json; charset=utf-8"}
            )
            
        if not device_id:
            return func.HttpResponse(
                json.dumps({"success": False, "error": "deviceId 파라미터가 필요합니다."}, ensure_ascii=False),
                status_code=400,
                headers={"Content-Type": "application/json; charset=utf-8"}
            )
        
        # 환경 변수에서 IoT Hub 연결 문자열 가져오기
        service_conn_str = os.environ.get("IOTHUB_SERVICE_CONNECTION_STRING")
        if not service_conn_str:
            logging.error("IOTHUB_SERVICE_CONNECTION_STRING 환경 변수가 설정되지 않았습니다.")
            return func.HttpResponse(
                json.dumps({"success": False, "error": "IoT Hub 연결 문자열이 설정되지 않았습니다."}, ensure_ascii=False),
                status_code=500,
                headers={"Content-Type": "application/json; charset=utf-8"}
            )
        
        # 명령어 분석
        command_action = analyze_command(command)
        if command_action:
            # 표준화된 명령어로 변환
            if command_action == "turn_on":
                final_command = "turn on the light"
            elif command_action == "turn_off":
                final_command = "turn off the light"
                
            logging.info(f"명령 처리: {command} -> {final_command} -> 디바이스: {device_id}")
        else:
            logging.warning(f"알 수 없는 명령: {command}")
            return func.HttpResponse(
                json.dumps({"success": False, "error": f"알 수 없는 조명 제어 명령입니다: {command}"}, ensure_ascii=False),
                status_code=400,
                headers={"Content-Type": "application/json; charset=utf-8"}
            )
        
        try:
            # IoT Hub Registry Manager 생성
            registry_manager = IoTHubRegistryManager(service_conn_str)
            
            # C2D 메시지 데이터 생성
            message_data = {
                "command": final_command,
                "originalCommand": command,
                "timestamp": req_body.get('timestamp'),
                "source": "AzureFunction"
            }
            message_str = json.dumps(message_data, ensure_ascii=False)
            
            # C2D 메시지 전송
            registry_manager.send_c2d_message(
                device_id, 
                message_str, 
                {
                    "content-type": "application/json",
                    "content-encoding": "utf-8"
                }
            )
            
            logging.info(f"IoT Hub로 메시지 전송 완료: {message_str}")
            
            # 성공 응답
            return func.HttpResponse(
                json.dumps({
                    "success": True,
                    "message": "IoT Hub로 메시지가 성공적으로 전송되었습니다.",
                    "originalCommand": command,
                    "finalCommand": final_command,
                    "deviceId": device_id,
                    "action": "조명 켜기" if command_action == "turn_on" else "조명 끄기"
                }, ensure_ascii=False),
                status_code=200,
                headers={"Content-Type": "application/json; charset=utf-8"}
            )
            
        except Exception as iot_error:
            logging.error(f"IoT Hub 통신 오류: {str(iot_error)}")
            return func.HttpResponse(
                json.dumps({"success": False, "error": f"IoT Hub 통신 오류: {str(iot_error)}"}, ensure_ascii=False),
                status_code=500,
                headers={"Content-Type": "application/json; charset=utf-8"}
            )
        
    except Exception as e:
        error_msg = f"Azure Function 실행 오류: {str(e)}"
        logging.error(error_msg)
        return func.HttpResponse(
            json.dumps({"success": False, "error": error_msg}, ensure_ascii=False),
            status_code=500,
            headers={"Content-Type": "application/json; charset=utf-8"}
        )

@app.function_name(name="ReceiveIoTMessages")
@app.route(route="receive-messages", methods=["GET", "POST"])
def receive_iot_messages(req: func.HttpRequest) -> func.HttpResponse:
    """
    IoT Hub로부터 C2D 메시지 수신을 시뮬레이션하는 엔드포인트 (테스트용)
    """
    logging.info('ReceiveIoTMessages HTTP trigger function processed a request.')
    
    try:
        device_conn_str = os.environ.get("IOTHUB_DEVICE_CONNECTION_STRING")
        if not device_conn_str:
            return func.HttpResponse(
                json.dumps({"success": False, "error": "IOTHUB_DEVICE_CONNECTION_STRING 환경 변수가 필요합니다."}, ensure_ascii=False),
                status_code=500,
                headers={"Content-Type": "application/json; charset=utf-8"}
            )
        
        return func.HttpResponse(
            json.dumps({
                "success": True,
                "message": "C2D 메시지 수신 기능은 별도의 디바이스 클라이언트에서 실행하세요.",
                "info": "이 엔드포인트는 테스트용입니다."
            }, ensure_ascii=False),
            status_code=200,
            headers={"Content-Type": "application/json; charset=utf-8"}
        )
        
    except Exception as e:
        error_msg = f"메시지 수신 오류: {str(e)}"
        logging.error(error_msg)
        return func.HttpResponse(
            json.dumps({"success": False, "error": error_msg}, ensure_ascii=False),
            status_code=500,
            headers={"Content-Type": "application/json; charset=utf-8"}
        )