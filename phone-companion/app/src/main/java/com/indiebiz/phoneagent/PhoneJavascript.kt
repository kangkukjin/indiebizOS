package com.indiebiz.phoneagent

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.webkit.WebView
import android.webkit.WebViewClient
import org.json.JSONObject
import org.json.JSONTokener
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/** Local JS compute only: no network, files, app bridge, or launcher cookies. */
object PhoneJavascript {
    private var context: Context? = null
    fun init(ctx: Context) { context = ctx.applicationContext }

    @JvmStatic
    fun evaluate(script: String): String {
        val ctx = context ?: return JSONObject().put("error", "JS context 미초기화").toString()
        if (Looper.myLooper() == Looper.getMainLooper()) {
            return JSONObject().put("error", "JS 계산은 작업 스레드에서 호출해야 합니다").toString()
        }
        if (script.length > 16 * 1024 * 1024) {
            return JSONObject().put("error", "JS 입력이 16MiB를 넘습니다").toString()
        }
        val latch = CountDownLatch(1)
        val done = AtomicBoolean(false)
        val handler = Handler(Looper.getMainLooper())
        var view: WebView? = null
        var output = JSONObject().put("error", "JS 계산 시간 초과(30초)").toString()
        handler.post {
            if (done.get()) return@post
            try {
                val web = WebView(ctx)
                view = web
                web.settings.javaScriptEnabled = true
                web.settings.blockNetworkLoads = true
                web.settings.allowFileAccess = false
                web.settings.allowContentAccess = false
                web.settings.domStorageEnabled = false
                web.webViewClient = object : WebViewClient() {
                    private var evaluated = false
                    override fun onPageFinished(w: WebView, url: String) {
                        if (evaluated || done.get()) return
                        evaluated = true
                        val code = """
                            (() => {
                              const lines = [];
                              const console = {log: (...v) => lines.push(v.join(' '))};
                              try {
                                $script
                                return JSON.stringify({stdout: lines.join('\n')});
                              } catch (e) { return JSON.stringify({error: String(e)}); }
                            })()
                        """.trimIndent()
                        w.evaluateJavascript(code) { result ->
                            if (done.compareAndSet(false, true)) {
                                output = try {
                                    val decoded = JSONTokener(result).nextValue()
                                    if (decoded is String) JSONObject(decoded).toString()
                                    else JSONObject().put("error", "JS 실행 결과가 없습니다").toString()
                                } catch (e: Exception) {
                                    JSONObject().put("error", "JS 결과 해석 실패: ${e.message}").toString()
                                }
                                latch.countDown()
                            }
                            w.destroy()
                            view = null
                        }
                    }
                }
                web.loadData("<html></html>", "text/html", "UTF-8")
            } catch (e: Exception) {
                if (done.compareAndSet(false, true)) {
                    output = JSONObject().put("error", "JS 초기화 실패: ${e.message}").toString()
                    latch.countDown()
                }
                view?.destroy()
                view = null
            }
        }
        if (!latch.await(30, TimeUnit.SECONDS)) {
            done.set(true)
            handler.post { view?.destroy(); view = null }
        }
        return output
    }
}
