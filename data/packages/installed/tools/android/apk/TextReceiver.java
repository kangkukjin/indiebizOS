package com.indiebiz.cliphelper;

import android.content.BroadcastReceiver;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

/**
 * ADB broadcast를 수신하여 텍스트를 처리하는 리시버
 *
 * ADB_INPUT_TEXT: IME의 commitText()로 직접 입력 (한글 OK)
 * ADB_SET_CLIPBOARD: 클립보드에 텍스트 설정 (백업용)
 */
public class TextReceiver extends BroadcastReceiver {
    private static final String TAG = "IndieBizIME";

    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent.getAction();
        if (action == null) {
            setResultCode(0);
            return;
        }

        String text = intent.getStringExtra("text");
        if (text == null) {
            // 호환성: "msg" 키도 지원 (ADBKeyboard 호환)
            text = intent.getStringExtra("msg");
        }
        if (text == null) {
            Log.w(TAG, "No text extra in broadcast");
            setResultCode(0);
            return;
        }

        if ("ADB_INPUT_TEXT".equals(action)) {
            // IME의 commitText()로 직접 입력
            if (IndieBizIME.commitTextFromReceiver(text)) {
                Log.d(TAG, "Text committed via IME: " + text);
                setResultCode(1);
            } else {
                Log.e(TAG, "Failed to commit text - IME not active or no input field");
                setResultCode(0);
            }
        } else if ("ADB_SET_CLIPBOARD".equals(action)) {
            // 클립보드에 텍스트 설정
            try {
                ClipboardManager clipboard = (ClipboardManager) context.getSystemService(Context.CLIPBOARD_SERVICE);
                if (clipboard != null) {
                    ClipData clip = ClipData.newPlainText("adb_clip", text);
                    clipboard.setPrimaryClip(clip);
                    Log.d(TAG, "Clipboard set: " + text);
                    setResultCode(1);
                } else {
                    setResultCode(0);
                }
            } catch (Exception e) {
                Log.e(TAG, "Clipboard error: " + e.getMessage());
                setResultCode(0);
            }
        }
    }
}
