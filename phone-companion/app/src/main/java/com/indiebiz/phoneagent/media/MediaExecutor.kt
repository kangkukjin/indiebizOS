package com.indiebiz.phoneagent.media

import java.util.concurrent.RejectedExecutionException

/** 세션 종료와 경합한 콜백·타이머 접수만 무시한다. 작업 본문의 다른 오류는 감추지 않는다. */
internal fun <T> submitMediaWork(submit: () -> T): T? = try {
    submit()
} catch (_: RejectedExecutionException) {
    null
}
