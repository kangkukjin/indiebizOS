"""조종실 모델 설명. 실제 해소 경로와 설정을 읽되 모델/네트워크는 호출하지 않는다."""
from pathlib import Path

import yaml

import model_resolver as models
from runtime_utils import get_base_path


AXIS_INFO = {
    "분류": {"label": "분류", "description": "실행·숙고 경로 선택과 기억 증류에 사용합니다."},
    "실행": {"label": "실행", "description": "도구 사용·결과물 작성·이미지 읽기와 채점. 이미지 입력이 가능한 모델을 우선합니다."},
    "의식": {"label": "의식", "description": "계획·중간 감독·재계획·최종 승인. 이미지가 첨부된 최종 검수는 별도 비전 모델을 사용합니다."},
    "평가": {"label": "보조 AI", "description": "노트북 답변·단계별 기준 검사·감독 없는 기존 평가에 사용합니다. 일반 작업의 최종 승인은 의식이 맡습니다."},
}


def _row(key, label, descriptor, policy, detail, source=""):
    # 설정 파일에 키·토큰이 있어도 이 명시적 허용 목록 밖 필드는 응답하지 않는다.
    return {"id": key, "label": label, "provider": descriptor.get("provider") or "",
            "model": descriptor.get("model") or "", "policy": policy,
            "detail": detail, "source": source or descriptor.get("source") or ""}


def describe_model_settings(gear):
    execution = models.resolve_image_execution()
    rows = [_row("image_execution", "이미지 읽기·채점", execution,
                 "실행 모델 우선", execution["image_reason"] + ". 에이전트 핀·수리 승격은 실제 실행 모델을 따릅니다.")]
    vision = models.resolve_vision()
    rows.append(_row("image_fallback", "별도 비전 모델", vision, "기어와 별도 · 조회 전용",
                     "실행 모델의 이미지 입력 미지원·미확인 때 대체합니다. 이미지 추출과 의식의 최종 시각 검수에도 사용합니다."))

    data = Path(get_base_path()) / "data"
    audio_path = data / "packages/installed/tools/android/audio_models.yaml"
    audio, audio_error = {}, ""
    try:
        audio = yaml.safe_load(audio_path.read_text(encoding="utf-8")) or {}
        if not isinstance(audio, dict):
            raise ValueError("오디오 설정 형식 오류")
    except (OSError, ValueError, yaml.YAMLError):
        audio_error = " 설정 파일이 없거나 읽을 수 없습니다."
    for mode, label, detail in (
            ("transcribe", "음성 받아쓰기", "파일·PC 마이크의 음성을 텍스트로 전사합니다."),
            ("analyze", "오디오 내용 분석", "음악·대화·소리의 내용을 질문에 맞춰 분석합니다.")):
        profile = audio.get(mode) or {}
        if not isinstance(profile, dict):
            profile = {}
        rows.append(_row("audio_" + mode, label,
                         {"provider": audio.get("provider"), "model": profile.get("model")},
                         "기어와 별도 · 조회 전용", detail + audio_error,
                         str(audio_path.relative_to(data))))
    for key, value in (gear.get("modality") or {}).items():
        if key in {"image", "_doc"}:
            continue
        label = {"embedding": "기억 검색 임베딩", "video": "동영상 모델"}.get(key, key)
        rows.append(_row("modality_" + key, label, {"model": value if isinstance(value, str) else ""},
                         "기어와 별도 · 조회 전용", "별도 설정값입니다." if value else "공통 모델 슬롯 미설정.",
                         "model_gear.json · modality." + key))
    return {"axis_info": AXIS_INFO, "sensory_models": rows}
