"""
prompt_benchmark.py - 프롬프트 레이턴시 벤치마크
IndieBiz OS

각 인지 에이전트의 프롬프트가 응답 속도에 미치는 영향을 정량 측정한다.
naked(프롬프트 없음) vs full(현재 프롬프트) 비교.

사용법:
    python3 prompt_benchmark.py                    # 전체 에이전트
    python3 prompt_benchmark.py --agents 무의식 평가  # 특정 에이전트만
    python3 prompt_benchmark.py --repeat 5          # 5회 반복
    python3 prompt_benchmark.py --input "오늘 날씨"  # 다른 입력으로 테스트
"""

import sys
import os
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# 프로젝트 경로
BASE_DIR = Path(__file__).parent.parent
BACKEND_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
PROMPTS_DIR = DATA_DIR / "common_prompts"
DOCS_DIR = DATA_DIR / "system_docs"
BENCHMARKS_DIR = DATA_DIR / "benchmarks"

# providers 임포트를 위해 경로 추가
sys.path.insert(0, str(BACKEND_DIR))


# ─── 설정 로더 ───

def load_config(name: str) -> dict:
    """AI config JSON 로드"""
    path = DATA_DIR / f"{name}.json"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_prompt_file(path: Path) -> str:
    """프롬프트 파일 읽기"""
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def estimate_tokens(text: str) -> int:
    """토큰 수 추정. 한국어 비율에 따라 가중치 적용."""
    if not text:
        return 0
    korean_chars = sum(1 for c in text if '\uac00' <= c <= '\ud7a3')
    total_chars = len(text)
    korean_ratio = korean_chars / max(total_chars, 1)
    # 한국어: ~1.5 chars/token, 영어: ~4 chars/token
    avg_chars_per_token = 4 - (korean_ratio * 2.5)
    return int(total_chars / avg_chars_per_token)


# ─── 에이전트 프롬프트 정의 ───

def get_agent_definitions() -> Dict[str, dict]:
    """각 에이전트의 설정 정의"""

    system_structure = load_prompt_file(DOCS_DIR / "system_structure.md")

    return {
        "무의식": {
            "config_name": "lightweight_ai_config",
            "system_prompt": load_prompt_file(PROMPTS_DIR / "unconscious_prompt.md"),
            "description": "요청 분류 (EXECUTE/THINK)",
        },
        "의식": {
            "config_name": "system_ai_config",
            "system_prompt": (
                load_prompt_file(PROMPTS_DIR / "consciousness_prompt.md")
                + "\n\n# 시스템 구조\n" + system_structure
            ),
            "description": "메타 판단 + 문제 정의",
        },
        "실행": {
            "config_name": "system_ai_config",
            "system_prompt": (
                load_prompt_file(PROMPTS_DIR / "base_prompt_v5.md")
                + "\n\n# 시스템 구조\n" + system_structure
            ),
            "description": "도구 사용 + 작업 실행",
        },
        "평가": {
            "config_name": "lightweight_ai_config",
            "system_prompt": load_prompt_file(PROMPTS_DIR / "evaluator_prompt.md"),
            "description": "달성 기준 평가",
        },
        "경험증류": {
            "config_name": "lightweight_ai_config",
            "system_prompt": load_prompt_file(PROMPTS_DIR / "reflection_prompt.md"),
            "description": "IBL 용례 증류",
        },
    }


# ─── 벤치마크 실행 ───

def create_provider(config: dict, system_prompt: str):
    """프로바이더 생성 + 초기화"""
    from providers import get_provider

    provider = get_provider(
        config.get("provider", "anthropic"),
        api_key=config.get("apiKey", ""),
        model=config.get("model", ""),
        system_prompt=system_prompt,
        tools=[],
    )
    provider.init_client()
    return provider


def measure_single_call(provider, message: str) -> Tuple[float, str]:
    """단일 API 호출 시간 측정. (ms, response_text) 반환."""
    start = time.perf_counter()
    response = provider.process_message(
        message=message,
        history=[],
        images=None,
        execute_tool=None,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    return elapsed_ms, response or ""


def run_benchmark_for_agent(
    agent_name: str,
    agent_def: dict,
    test_input: str,
    repeat: int,
) -> dict:
    """한 에이전트의 naked vs full 벤치마크 실행"""

    config = load_config(agent_def["config_name"])
    if not config.get("apiKey"):
        return {"error": f"API 키 없음 ({agent_def['config_name']})"}

    full_prompt = agent_def["system_prompt"]
    prompt_tokens = estimate_tokens(full_prompt)

    print(f"\n{'─'*50}")
    print(f"  {agent_name} ({agent_def['description']})")
    print(f"  모델: {config.get('provider')}:{config.get('model')}")
    print(f"  프롬프트: ~{prompt_tokens} tokens ({len(full_prompt)} chars)")
    print(f"{'─'*50}")

    # A. Naked (프롬프트 없음)
    naked_times = []
    print(f"  [naked] ", end="", flush=True)
    for i in range(repeat):
        try:
            provider = create_provider(config, system_prompt="")
            ms, _ = measure_single_call(provider, test_input)
            naked_times.append(ms)
            print(f"{ms:.0f}ms ", end="", flush=True)
        except Exception as e:
            print(f"ERR({e}) ", end="", flush=True)
    print()

    # B. Full (현재 프롬프트)
    full_times = []
    print(f"  [full]  ", end="", flush=True)
    for i in range(repeat):
        try:
            provider = create_provider(config, system_prompt=full_prompt)
            ms, _ = measure_single_call(provider, test_input)
            full_times.append(ms)
            print(f"{ms:.0f}ms ", end="", flush=True)
        except Exception as e:
            print(f"ERR({e}) ", end="", flush=True)
    print()

    # 통계 계산
    def stats(times):
        if not times:
            return {"avg": 0, "min": 0, "max": 0, "values": []}
        return {
            "avg": sum(times) / len(times),
            "min": min(times),
            "max": max(times),
            "values": [round(t, 1) for t in times],
        }

    naked_stats = stats(naked_times)
    full_stats = stats(full_times)

    diff_ms = full_stats["avg"] - naked_stats["avg"]
    ratio = full_stats["avg"] / naked_stats["avg"] if naked_stats["avg"] > 0 else 0

    return {
        "agent": agent_name,
        "description": agent_def["description"],
        "model": f"{config.get('provider')}:{config.get('model')}",
        "prompt_chars": len(full_prompt),
        "prompt_tokens_est": prompt_tokens,
        "naked": naked_stats,
        "full": full_stats,
        "diff_ms": round(diff_ms, 1),
        "ratio": round(ratio, 2),
    }


# ─── 출력 포맷팅 ───

def print_summary_table(results: List[dict]):
    """결과 요약 테이블 출력"""
    print("\n")
    print("=" * 80)
    print("  IndieBiz OS 프롬프트 레이턴시 벤치마크 결과")
    print("=" * 80)
    print()

    # 헤더
    print(f"  {'에이전트':<8} {'naked(ms)':>10} {'full(ms)':>10} {'차이(ms)':>10} {'배율':>6} {'프롬프트':>8}")
    print(f"  {'':─<8} {'':─>10} {'':─>10} {'':─>10} {'':─>6} {'':─>8}")

    total_naked = 0
    total_full = 0

    for r in results:
        if "error" in r:
            print(f"  {r.get('agent', '?'):<8} {'에러: ' + r['error']}")
            continue

        naked_avg = r["naked"]["avg"]
        full_avg = r["full"]["avg"]
        total_naked += naked_avg
        total_full += full_avg

        print(
            f"  {r['agent']:<8}"
            f" {naked_avg:>9.0f}"
            f" {full_avg:>9.0f}"
            f" {r['diff_ms']:>+9.0f}"
            f" {r['ratio']:>5.1f}x"
            f" {r['prompt_tokens_est']:>7}"
        )

    if total_naked > 0:
        print(f"  {'':─<8} {'':─>10} {'':─>10} {'':─>10} {'':─>6} {'':─>8}")
        diff_total = total_full - total_naked
        ratio_total = total_full / total_naked if total_naked else 0
        print(
            f"  {'합계':<8}"
            f" {total_naked:>9.0f}"
            f" {total_full:>9.0f}"
            f" {diff_total:>+9.0f}"
            f" {ratio_total:>5.1f}x"
            f" {'':>7}"
        )

    print()
    print("  * naked = 시스템 프롬프트 없이 같은 모델 호출")
    print("  * full  = 현재 시스템 프롬프트 포함 호출")
    print("  * 프롬프트 = 추정 토큰 수 (한국어 가중치 적용)")
    print()


def save_results(results: List[dict], test_input: str, repeat: int):
    """결과를 JSON 파일로 저장"""
    BENCHMARKS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = BENCHMARKS_DIR / f"prompt_latency_{timestamp}.json"

    output = {
        "timestamp": datetime.now().isoformat(),
        "test_input": test_input,
        "repeat": repeat,
        "results": results,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"  결과 저장: {filepath}")
    return filepath


# ─── 메인 ───

def main():
    parser = argparse.ArgumentParser(description="IndieBiz OS 프롬프트 레이턴시 벤치마크")
    parser.add_argument("--agents", nargs="*", help="테스트할 에이전트 (기본: 전체)")
    parser.add_argument("--repeat", type=int, default=3, help="반복 횟수 (기본: 3)")
    parser.add_argument("--input", type=str, default="안녕", help="테스트 입력 (기본: 안녕)")
    parser.add_argument("--no-save", action="store_true", help="결과 파일 저장 안 함")
    args = parser.parse_args()

    print()
    print("  IndieBiz OS 프롬프트 레이턴시 벤치마크")
    print(f"  입력: \"{args.input}\" | 반복: {args.repeat}회")

    definitions = get_agent_definitions()

    # 에이전트 필터
    if args.agents:
        targets = {k: v for k, v in definitions.items() if k in args.agents}
        if not targets:
            print(f"  에이전트를 찾을 수 없습니다: {args.agents}")
            print(f"  사용 가능: {list(definitions.keys())}")
            sys.exit(1)
    else:
        targets = definitions

    # 벤치마크 실행
    results = []
    for name, defn in targets.items():
        result = run_benchmark_for_agent(name, defn, args.input, args.repeat)
        results.append(result)

    # 결과 출력
    print_summary_table(results)

    # 저장
    if not args.no_save:
        save_results(results, args.input, args.repeat)


if __name__ == "__main__":
    main()
