package com.indiebiz.phoneagent

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.ViewGroup
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import com.chaquo.python.Python

/**
 * indiebizOS 런처 3표면(자율주행/수동/앱)을 폰 안에 띄우는 WebView.
 * 백엔드(127.0.0.1:8765)는 App 이 포그라운드 진입 시 기동하므로, 여기선 준비될 때까지
 * 기다렸다 로드한다(자동시작과의 race 방지). 소켓 바인드 지연은 onReceivedError 재시도로 흡수.
 */
class LauncherActivity : Activity() {
    private lateinit var web: WebView
    private val handler = Handler(Looper.getMainLooper())
    private var tries = 0

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        web = WebView(this).apply {
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
            settings.apply {
                javaScriptEnabled = true
                domStorageEnabled = true        // 앱모드 계기 상태(localStorage)
                useWideViewPort = true
                loadWithOverviewMode = true
                cacheMode = WebSettings.LOAD_DEFAULT
            }
            webViewClient = object : WebViewClient() {
                // 런처 자신(127.0.0.1)만 WebView 안에서. 외부 사이트(즐겨찾기 등)는 시스템 브라우저로
                // → 런처 SPA 가 안 깨지고 뒤로가기도 정상(외부는 별도 앱).
                override fun shouldOverrideUrlLoading(view: WebView, req: WebResourceRequest): Boolean {
                    val host = req.url.host ?: ""
                    if (host == "127.0.0.1" || host == "localhost") return false
                    return try {
                        startActivity(Intent(Intent.ACTION_VIEW, req.url).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                        true
                    } catch (_: Exception) { false }
                }
                override fun onReceivedError(view: WebView, req: WebResourceRequest?, err: WebResourceError?) {
                    // 백엔드 소켓이 아직 안 떴으면 잠시 후 재시도(메인 프레임만).
                    if (req?.isForMainFrame == true && tries < 30) {
                        tries++
                        handler.postDelayed({ view.loadUrl(Config.LAUNCHER_URL) }, 400)
                    }
                }
            }
            webChromeClient = WebChromeClient()  // <input>/JS dialog/진행률
        }
        setContentView(web)
        loadWhenReady()
    }

    /** phone_api.is_serving() 이 true 가 될 때까지 기다렸다 로드. */
    private fun loadWhenReady() {
        val serving = try {
            Python.getInstance().getModule("phone_api").callAttr("is_serving").toBoolean()
        } catch (_: Throwable) { false }

        if (serving || tries >= 30) {
            web.loadUrl(Config.LAUNCHER_URL)   // 소켓 지연은 onReceivedError 가 재시도
        } else {
            tries++
            handler.postDelayed({ loadWhenReady() }, 300)
        }
    }

    @Suppress("DEPRECATION")
    override fun onBackPressed() {
        if (web.canGoBack()) web.goBack() else super.onBackPressed()
    }
}
