package com.indiebiz.cliphelper;

import android.inputmethodservice.InputMethodService;
import android.util.Log;
import android.view.inputmethod.InputConnection;

/**
 * IndieBiz IME - ADB를 통한 텍스트 주입용 최소 IME
 *
 * 이 IME는 키보드 UI를 표시하지 않습니다.
 * ADB broadcast로 텍스트를 수신하면 commitText()로 직접 입력합니다.
 *
 * 사용법:
 * 1. adb shell ime set com.indiebiz.cliphelper/.IndieBizIME
 * 2. adb shell am broadcast -a ADB_INPUT_TEXT --es text '한글텍스트' -n com.indiebiz.cliphelper/.TextReceiver
 * 3. adb shell ime set com.samsung.android.honeyboard/.service.HoneyBoardService  (삼성 키보드 복원)
 */
public class IndieBizIME extends InputMethodService {
    private static final String TAG = "IndieBizIME";
    private static IndieBizIME sInstance = null;

    @Override
    public void onCreate() {
        super.onCreate();
        sInstance = this;
        Log.d(TAG, "IME created");
    }

    @Override
    public void onDestroy() {
        sInstance = null;
        Log.d(TAG, "IME destroyed");
        super.onDestroy();
    }

    /**
     * TextReceiver에서 호출 - 현재 포커스된 입력 필드에 텍스트를 직접 주입
     */
    public static boolean commitTextFromReceiver(String text) {
        if (sInstance == null) {
            Log.e(TAG, "IME instance is null - IME not active");
            return false;
        }

        InputConnection ic = sInstance.getCurrentInputConnection();
        if (ic == null) {
            Log.e(TAG, "InputConnection is null - no focused input field");
            return false;
        }

        boolean result = ic.commitText(text, 1);
        Log.d(TAG, "commitText result=" + result + " text=" + text);
        return result;
    }

    /**
     * IME가 활성화되었는지 확인
     */
    public static boolean isActive() {
        return sInstance != null;
    }
}
