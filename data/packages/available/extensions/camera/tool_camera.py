"""
카메라 입력 도구
Camera Input Tool for IndieBiz

AI 에이전트가 PC의 웹캠을 통해 이미지를 캡처할 수 있게 합니다.

기능:
- capture_camera: 카메라로 사진 촬영
- list_cameras: 사용 가능한 카메라 목록

참고: 미리보기 기능은 프론트엔드(Electron)의 CameraPreview 컴포넌트에서 제공합니다.
"""

import cv2
import base64
import os
from datetime import datetime
from pathlib import Path


def list_cameras(max_check: int = 5) -> dict:
    """사용 가능한 카메라 목록 조회"""
    available = []

    for i in range(max_check):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                available.append({
                    "index": i,
                    "resolution": f"{width}x{height}",
                    "name": f"Camera {i}" if i > 0 else "Default Camera"
                })
            cap.release()

    return {
        "success": True,
        "cameras": available,
        "message": f"{len(available)}개의 카메라를 찾았습니다." if available else "사용 가능한 카메라가 없습니다."
    }


def capture_image(
    camera_index: int = 0,
    save_path: str = None,
    return_base64: bool = True,
    warmup_frames: int = 5
) -> dict:
    """카메라로 사진 촬영"""
    cap = None
    try:
        cap = cv2.VideoCapture(camera_index)

        if not cap.isOpened():
            return {
                "success": False,
                "message": f"카메라 {camera_index}를 열 수 없습니다.",
                "hint": "카메라 권한을 확인하세요."
            }

        # 카메라 워밍업
        for _ in range(warmup_frames):
            cap.read()

        ret, frame = cap.read()

        if not ret or frame is None:
            return {
                "success": False,
                "message": "프레임을 읽을 수 없습니다."
            }

        # 저장 경로 생성
        if save_path is None:
            outputs_dir = Path(__file__).parent / "outputs"
            outputs_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = str(outputs_dir / f"camera_{timestamp}.jpg")

        cv2.imwrite(save_path, frame)

        result = {
            "success": True,
            "file_path": save_path,
            "resolution": f"{frame.shape[1]}x{frame.shape[0]}",
            "message": f"사진이 저장되었습니다: {save_path}"
        }

        if return_base64:
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            b64_image = base64.b64encode(buffer).decode('utf-8')
            result["base64"] = b64_image
            result["media_type"] = "image/jpeg"

        return result

    except Exception as e:
        return {
            "success": False,
            "message": f"카메라 오류: {str(e)}"
        }
    finally:
        if cap is not None:
            cap.release()


def capture_for_ai(camera_index: int = 0) -> dict:
    """AI 분석용 이미지 캡처"""
    result = capture_image(camera_index=camera_index, return_base64=True)

    if result["success"]:
        file_path = result["file_path"]
        return {
            "success": True,
            "image_data": {
                "type": "base64",
                "media_type": result["media_type"],
                "data": result["base64"]
            },
            "file_path": file_path,
            "message": f"이미지가 캡처되었습니다. 파일 경로: {file_path}"
        }
    else:
        return result


# 도구 정의 (Claude Tool Use 형식)
CAMERA_TOOLS = [
    {
        "name": "capture_camera",
        "description": """PC 카메라로 사진을 촬영합니다.

현재 카메라에 보이는 장면을 즉시 촬영하여 이미지 파일로 저장합니다.
촬영된 이미지는 AI가 분석할 수 있는 형식으로 반환됩니다.

중요: 촬영 후 응답할 때 반드시 file_path를 그대로 포함하세요. 예: "촬영된 이미지: /path/to/image.jpg"
이렇게 해야 사용자가 이미지를 볼 수 있습니다.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "camera_index": {
                    "type": "integer",
                    "description": "카메라 인덱스 (기본값: 0)",
                    "default": 0
                }
            },
            "required": []
        }
    },
    {
        "name": "list_cameras",
        "description": "PC에 연결된 카메라 목록을 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]


def use_tool(tool_name: str, tool_input: dict) -> dict:
    """도구 실행 함수"""
    if tool_name == "capture_camera":
        camera_index = tool_input.get("camera_index", 0)
        return capture_for_ai(camera_index)
    elif tool_name == "list_cameras":
        return list_cameras()
    else:
        return {"success": False, "message": f"알 수 없는 도구: {tool_name}"}


if __name__ == "__main__":
    print("=== 카메라 테스트 ===\n")

    # 카메라 목록
    cameras = list_cameras()
    print(f"카메라 목록: {cameras}\n")

    # 사진 촬영
    if cameras.get("cameras"):
        result = capture_for_ai(0)
        if result.get("success"):
            print(f"✅ 촬영 완료: {result.get('file_path')}")
        else:
            print(f"❌ 촬영 실패: {result.get('message')}")
    else:
        print("사용 가능한 카메라가 없습니다.")
