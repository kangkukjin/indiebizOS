"""[sense:listen] 파일 경로: 구간별 처리·증거 저장·재사용·부분 재개를 소유한다."""
import hashlib
import json
import os
import tempfile
import time
import uuid
from pathlib import Path

from filelock import FileLock, Timeout

from android_audio_provider import analyze_clip, profile, settings
from android_audio_signal import clip, file_hash, inspect_signal, number, probe, ranges

SCHEMA_VERSION = 1


def _atomic(path, value):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    os.replace(temporary, path)


def _progress(stage, **fields):
    from ibl_progress import beat
    from episode_logger import record_trajectory_event
    detail = {"audio_stage": stage, **fields}
    beat(detail)
    record_trajectory_event("audio.progress", detail)


def _cancelled():
    from supervision_bus import current
    controller = current()
    return bool(controller and controller.cancelled())


def listen_file(args, context, op="transcribe"):
    """파일 인자가 잘못되면 마이크로 폴백하지 않는다. 실패는 partial/failed로 명시한다."""
    try:
        return _listen_file(args, context, op)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        return {"success": False, "status": "failed", "error": str(exc), "items": []}


def _listen_file(args, context, op):
    from runtime_utils import get_base_path

    raw = args.get("path")
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("path는 오디오/영상 파일 경로 문자열이어야 합니다")
    source = Path(context.resolve_path(raw)).resolve()
    if not source.is_file():
        raise ValueError(f"오디오 파일이 없습니다: {source}")
    if op == "record":
        raise ValueError("record는 마이크 녹음입니다. 파일은 transcribe/analyze/inspect로 읽으세요")
    if op not in {"transcribe", "analyze", "inspect"}:
        raise ValueError("파일 듣기는 transcribe/analyze/inspect를 지원합니다")
    question = args.get("question") or ""
    if op == "analyze" and not question:
        question = "들리는 소리를 설명하고 대화·노래·반주·무음 구간을 구분해주세요."
    instruction = args.get("instruction") or ""
    if not isinstance(question, str) or not isinstance(instruction, str):
        raise ValueError("question/instruction은 문자열이어야 합니다")
    if args.get("timestamps") and op != "transcribe":
        raise ValueError("timestamps는 전사의 단어 시각 옵션입니다")
    config = settings()
    segment = number(args.get("segment_seconds", config["segment_seconds"]), "segment_seconds")
    if not 5 <= segment <= 300:
        raise ValueError("segment_seconds는 5~300초여야 합니다")
    chosen = profile(op, args.get("model"), instruction) if op != "inspect" else {}
    if args.get("timestamps") and chosen.get("api") != "interactions":
        raise ValueError("이 전사 모델은 단어 시각을 지원하지 않습니다. 기본 전사 모델을 사용하세요")
    started = time.monotonic()
    deadline = started + config["call_budget_s"]
    metadata = probe(source)
    selected = ranges(args, metadata["duration"])
    before = source.stat()
    source_hash = file_hash(source)
    cache = get_base_path() / "data" / "audio_cache" / source_hash
    cache.mkdir(parents=True, exist_ok=True)
    chunks = []
    for start, end in selected:
        while start < end - 0.001:
            stop = end if op == "inspect" else min(end, start + segment)
            chunks.append((start, stop))
            start = stop
    signature = {"schema": SCHEMA_VERSION, "source_hash": source_hash, "op": op, "ranges": selected,
                 "profile": chosen, "question": question, "instruction": instruction,
                 "timestamps": bool(args.get("timestamps")), "segment_seconds": segment}
    request_id = hashlib.sha256(json.dumps(signature, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    result_file = cache / (request_id + ".result.json")
    # 출력을 원본 위에 쓰지 않는다. 장문은 저장하고 도구 응답은 미리보기/증거 경로만 준다.
    transcript_file = None
    if op == "transcribe":
        if args.get("out"):
            resolved = context.resolve_output_path(args["out"], ext=".txt")
            if resolved.get("error"):
                raise ValueError(resolved["error"])
            transcript_file = Path(resolved["path"])
        else:
            transcript_file = Path(context.output_dir("transcripts")) / (source.stem + "." + request_id[:12] + ".txt")
        if transcript_file.resolve() == source:
            raise ValueError("전사문 출력 경로가 원본 오디오와 같습니다")
    rows, complete, texts, failures = [], [], [], []
    cached_count, calls = 0, 0
    usage = {"input": 0, "output": 0}
    _progress("started", source=str(source), op=op, chunks=len(chunks), result_path=str(result_file))
    with tempfile.TemporaryDirectory(prefix="listen_") as work:
        for index, (start, end) in enumerate(chunks):
            if _cancelled() or time.monotonic() >= deadline - 15:
                failures.append("취소/호출 시간 예산 소진. 동일 요청을 재호출하면 완료된 구간을 재사용합니다")
                break
            key_data = {**signature, "ranges": [(start, end)]}
            key = hashlib.sha256(json.dumps(key_data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            saved = cache / (key + ".chunk.json")
            try:
                with FileLock(str(saved) + ".lock", timeout=min(5, max(0, deadline - time.monotonic()))):
                    if saved.exists() and not args.get("refresh", False):
                        value = json.loads(saved.read_text(encoding="utf-8"))
                        cached_count += 1
                    else:
                        _progress("processing", chunk=index + 1, chunks=len(chunks), start=start, end=end,
                                  completed_seconds=sum(b - a for a, b in complete))
                        remaining = min(config["request_timeout_s"], deadline - time.monotonic() - 5)
                        if op == "inspect":
                            value = {"signal": inspect_signal(source, start, end, metadata, remaining)}
                        else:
                            local = Path(work) / "clip.flac"
                            clip(source, local, start, end, remaining)
                            remaining = min(config["request_timeout_s"], deadline - time.monotonic() - 5)
                            if remaining <= 1 or _cancelled():
                                raise ValueError("오디오 요청 전 취소/시간 예산 소진")
                            calls += 1
                            value = analyze_clip(local, end - start, op, chosen, question, instruction,
                                                 bool(args.get("timestamps")), remaining)
                            if value.get("usage") is None:
                                usage = None
                            elif usage is not None:
                                for field in usage:
                                    usage[field] += value["usage"].get(field, 0)
                        _atomic(saved, value)
            except Timeout:
                failures.append("같은 오디오 구간을 이미 분석 중입니다. 중복 요청을 시작하지 않았습니다")
                break
            except (ValueError, OSError, TypeError, KeyError) as exc:
                if calls:
                    usage = None  # 실패 응답의 비용을 0으로 단정하지 않는다. 공급자 원장에는 관측분 기록.
                failures.append(str(exc))
                break
            if op == "inspect":
                rows.append(value["signal"])
            else:
                texts.append(value.get("text", ""))
                events = value.get("events") or []
                if events:
                    rows.extend({**e, "start": e["start"] + start, "end": e["end"] + start,
                                 "timing": value["timing"]} for e in events)
                else:
                    rows.append({"start": start, "end": end, "text": value.get("text", ""),
                                 "kind": "unknown", "timing": "chunk"})
                if value.get("answer") or value.get("uncertain"):
                    rows.append({"start": start, "end": end, "answer": value.get("answer", ""),
                                 "uncertain": value.get("uncertain", False), "kind": "assessment"})
            complete.append((start, end))
            _atomic(result_file, {"status": "processing", **signature, "completed_ranges": complete, "items": rows})
            _progress("chunk_done", chunk=index + 1, chunks=len(chunks), cached_chunks=cached_count,
                      completed_seconds=sum(b - a for a, b in complete))
    after = source.stat()
    if _cancelled():
        failures.append("사용자가 작업을 취소했습니다")
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        failures.append("검사 도중 원본 파일이 바뀌었습니다. 현재 파일을 다시 검사해야 합니다")
    success = not failures and len(complete) == len(chunks)
    result = {"success": success, "status": "completed" if success else "partial" if complete else "failed",
              "source": str(source), "source_hash": source_hash, "op": op, "metadata": metadata,
              "requested_ranges": selected, "completed_ranges": complete,
              "coverage": "whole_file" if success and selected == [(0, metadata["duration"])] else "selected_or_partial",
              "items": rows, "result_path": str(result_file), "cached_chunks": cached_count,
              "model_calls": calls, "usage_this_call": usage, "elapsed_s": round(time.monotonic() - started, 3)}
    if failures:
        result.update(error="; ".join(failures), resume_hint="같은 인자로 다시 호출하세요. refresh는 지정하지 마세요.")
    if success and transcript_file:
        full = "\n\n".join(texts)
        transcript_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = transcript_file.with_name(transcript_file.name + "." + uuid.uuid4().hex + ".tmp")
        temporary.write_text(full, encoding="utf-8")
        os.replace(temporary, transcript_file)
        result.update(transcript_path=str(transcript_file), chars=len(full))
    _atomic(result_file, result)
    _progress(result["status"], result_path=str(result_file), completed_chunks=len(complete),
              model_calls=calls, cached_chunks=cached_count)
    # 원문은 result_path에 보존. 미리보기 축약 여부를 명시해 같은 오디오를 다시 보내지 않게 한다.
    preview, size = [], 0
    for row in rows:
        item = dict(row)
        for field in ("text", "answer"):
            if len(item.get(field, "")) > 1000:
                item[field] = item[field][:1000]
                item["truncated"] = True
        if len(preview) >= 20 or size + len(json.dumps(item, ensure_ascii=False)) > 6000:
            break
        preview.append(item)
        size += len(json.dumps(item, ensure_ascii=False))
    return {**result, "items": preview, "total_items": len(rows),
            "truncated": len(preview) < len(rows) or any(i.get("truncated") for i in preview)}
