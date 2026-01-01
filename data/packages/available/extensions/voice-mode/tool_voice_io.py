"""
음성 입출력 표준 도구 (Whisper Small 버전)
Standard Tool for Voice Input/Output with Whisper

Commands:
- listen: 음성 입력을 텍스트로 변환 (Whisper Small 사용)
- speak: 텍스트를 음성으로 출력
- start_listening: 연속 음성 입력 모드 시작
- stop_listening: 연속 음성 입력 모드 중지
"""

import speech_recognition as sr
import pyttsx3
import threading
import queue
import time
import whisper
import numpy as np

class VoiceIO:
    def __init__(self):
        # 음성 인식기 초기화
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        
        # Whisper 모델 로드 (small 모델 - 한국어 인식 필수)
        try:
            print("🔄 Whisper Small 모델 로딩 중...")
            self.whisper_model = whisper.load_model("small")
            self.use_whisper = True
            print("✅ Whisper Small 모델 로드 완료 (오프라인 STT)")
        except Exception as e:
            print(f"⚠️ Whisper 로드 실패: {e}")
            print("   → Google API로 폴백합니다")
            self.use_whisper = False
        
        # 음성 합성 엔진 초기화
        self.tts_engine = pyttsx3.init()
        self.tts_engine.setProperty('rate', 150)  # 속도
        self.tts_engine.setProperty('volume', 0.9)  # 볼륨
        
        # 한국어 음성 설정 (가능한 경우)
        voices = self.tts_engine.getProperty('voices')
        for voice in voices:
            if 'korean' in voice.name.lower() or 'ko' in voice.languages:
                self.tts_engine.setProperty('voice', voice.id)
                break
        
        # 연속 듣기 모드
        self.is_listening = False
        self.listen_thread = None
        self.audio_queue = queue.Queue()
        
        # 마이크 노이즈 조정
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=1)
        
        # 에너지 임계값 수동 설정 (매우 낮게)
        self.recognizer.energy_threshold = 100  # 매우 낮게 설정 (MacBook Air 마이크용)
        self.recognizer.dynamic_energy_threshold = False  # 고정 임계값 사용
        self.recognizer.pause_threshold = 0.5  # 말 멈춤 감지 시간 단축 (0.8 → 0.5초)
    
    def listen_once(self, language='ko-KR', timeout=5):
        """
        한 번 음성 입력 받기 (Whisper 또는 Google API)
        
        Args:
            language: 인식 언어 (기본값: 한국어)
            timeout: 최대 대기 시간 (초)
        
        Returns:
            인식된 텍스트 또는 None
        """
        try:
            with self.microphone as source:
                print("🎤 듣고 있습니다... (임계값: {})" .format(self.recognizer.energy_threshold))
                print("   큰 소리로 말씀하세요!")
                
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=10)
                
            print("🔄 음성 인식 중...")
            
            # Whisper 사용 가능하면 우선 사용
            if self.use_whisper:
                # 오디오 데이터를 numpy 배열로 변환
                audio_data = np.frombuffer(audio.get_raw_data(), np.int16)
                audio_float = audio_data.astype(np.float32) / 32768.0

                # 샘플레이트 변환 (Whisper는 16kHz 필요)
                sample_rate = audio.sample_rate
                if sample_rate != 16000:
                    import soxr
                    audio_float = soxr.resample(audio_float, sample_rate, 16000)

                # Whisper로 인식
                lang_code = 'ko' if language.startswith('ko') else 'en'
                result = self.whisper_model.transcribe(
                    audio_float,
                    language=lang_code,
                    fp16=False  # CPU 사용 시
                )
                text = result['text'].strip()
                print(f"✅ 인식됨 (Whisper): {text}")
                return text
            else:
                # 폴백: Google API
                text = self.recognizer.recognize_google(audio, language=language)
                print(f"✅ 인식됨 (Google): {text}")
                return text
            
        except sr.WaitTimeoutError:
            print("⏱️ 타임아웃: 음성이 감지되지 않았습니다.")
            return None
        except sr.UnknownValueError:
            print("❌ 음성을 인식할 수 없습니다.")
            return None
        except sr.RequestError as e:
            print(f"❌ 음성 인식 서비스 오류: {e}")
            return None
        except Exception as e:
            print(f"❌ 오류: {e}")
            return None
    
    def speak(self, text):
        """
        텍스트를 음성으로 출력
        
        Args:
            text: 출력할 텍스트
        """
        try:
            print(f"🔊 말하기: {text}")
            self.tts_engine.say(text)
            self.tts_engine.runAndWait()
            return True
        except Exception as e:
            print(f"❌ 음성 출력 오류: {e}")
            return False
    
    def start_continuous_listening(self, language='ko-KR'):
        """연속 듣기 모드 시작"""
        if self.is_listening:
            return False
        
        self.is_listening = True
        self.listen_thread = threading.Thread(
            target=self._continuous_listen_loop,
            args=(language,),
            daemon=True
        )
        self.listen_thread.start()
        print("🎤 연속 듣기 모드 시작")
        return True
    
    def stop_continuous_listening(self):
        """연속 듣기 모드 중지"""
        if not self.is_listening:
            return False
        
        self.is_listening = False
        if self.listen_thread:
            self.listen_thread.join(timeout=2)
        print("🛑 연속 듣기 모드 중지")
        return True
    
    def _continuous_listen_loop(self, language):
        """연속 듣기 루프 (백그라운드 스레드)"""
        while self.is_listening:
            try:
                with self.microphone as source:
                    audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=10)
                    
                # Whisper 사용 가능하면 우선 사용
                if self.use_whisper:
                    audio_data = np.frombuffer(audio.get_raw_data(), np.int16)
                    audio_float = audio_data.astype(np.float32) / 32768.0
                    lang_code = 'ko' if language.startswith('ko') else 'en'
                    result = self.whisper_model.transcribe(
                        audio_float, 
                        language=lang_code,
                        fp16=False
                    )
                    text = result['text'].strip()
                    self.audio_queue.put(text)
                else:
                    # 폴백: Google API
                    text = self.recognizer.recognize_google(audio, language=language)
                    self.audio_queue.put(text)
            except sr.WaitTimeoutError:
                continue
            except sr.UnknownValueError:
                continue
            except Exception as e:
                print(f"❌ 연속 듣기 오류: {e}")
                time.sleep(0.1)
    
    def get_recognized_text(self):
        """큐에서 인식된 텍스트 가져오기"""
        try:
            return self.audio_queue.get_nowait()
        except queue.Empty:
            return None


# 전역 인스턴스
_voice_io = None

def get_voice_io():
    """VoiceIO 싱글톤 인스턴스 가져오기"""
    global _voice_io
    if _voice_io is None:
        _voice_io = VoiceIO()
    return _voice_io


def tool_voice_io(command, send_to=None, comment=None, text=None, language='ko-KR', timeout=5):
    """
    음성 입출력 표준 도구
    
    Args:
        command: 명령어
            - "listen": 한 번 음성 입력 받기
            - "speak": 텍스트를 음성으로 출력
            - "start_listening": 연속 듣기 시작
            - "stop_listening": 연속 듣기 중지
            - "get_text": 인식된 텍스트 가져오기 (연속 듣기 모드)
        send_to: 다음 도구 (표준 도구 패턴)
        comment: 주석
        text: speak 명령시 출력할 텍스트
        language: 인식 언어 (기본값: ko-KR)
        timeout: listen 명령시 최대 대기 시간
    
    Returns:
        [command, send_to, comment, result]
    """
    voice_io = get_voice_io()
    result = None
    
    if command == "listen":
        # 한 번 음성 입력
        recognized_text = voice_io.listen_once(language=language, timeout=timeout)
        result = {
            "status": "success" if recognized_text else "no_input",
            "text": recognized_text,
            "message": f"인식됨: {recognized_text}" if recognized_text else "음성 입력 없음"
        }
    
    elif command == "speak":
        # 텍스트 음성 출력
        if not text:
            result = {
                "status": "error",
                "message": "출력할 텍스트가 필요합니다."
            }
        else:
            success = voice_io.speak(text)
            result = {
                "status": "success" if success else "error",
                "text": text,
                "message": "음성 출력 완료" if success else "음성 출력 실패"
            }
    
    elif command == "start_listening":
        # 연속 듣기 모드 시작
        success = voice_io.start_continuous_listening(language=language)
        result = {
            "status": "success" if success else "already_running",
            "message": "연속 듣기 모드 시작" if success else "이미 실행 중"
        }
    
    elif command == "stop_listening":
        # 연속 듣기 모드 중지
        success = voice_io.stop_continuous_listening()
        result = {
            "status": "success" if success else "not_running",
            "message": "연속 듣기 모드 중지" if success else "실행 중이 아님"
        }
    
    elif command == "get_text":
        # 인식된 텍스트 가져오기 (연속 듣기 모드)
        recognized_text = voice_io.get_recognized_text()
        result = {
            "status": "success" if recognized_text else "no_input",
            "text": recognized_text,
            "message": f"인식됨: {recognized_text}" if recognized_text else "대기 중인 텍스트 없음"
        }
    
    else:
        result = {
            "status": "error",
            "message": f"알 수 없는 명령어: {command}"
        }
    
    return [command, send_to, comment, result]


if __name__ == "__main__":
    # 테스트 코드
    print("=== 음성 입출력 도구 테스트 (Whisper Base) ===\n")
    
    # 테스트 1: 음성 출력
    print("1. 음성 출력 테스트")
    result = tool_voice_io("speak", text="안녕하세요. Whisper Base 모델 테스트입니다.")
    print(f"결과: {result}\n")
    
    # 테스트 2: 음성 입력
    print("2. 음성 입력 테스트 (5초 안에 말씀하세요)")
    result = tool_voice_io("listen", timeout=5)
    print(f"결과: {result}\n")
    
    # 테스트 3: 연속 듣기 모드
    print("3. 연속 듣기 모드 테스트 (10초간 여러 번 말할 수 있습니다)")
    tool_voice_io("start_listening")
    
    for i in range(10):
        time.sleep(1)
        result = tool_voice_io("get_text")
        if result[3]["text"]:
            print(f"인식: {result[3]['text']}")
    
    tool_voice_io("stop_listening")
    print("\n테스트 완료!")
