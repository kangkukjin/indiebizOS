package com.indiebiz.phoneagent

import android.annotation.SuppressLint
import android.app.Activity
import com.indiebiz.ui.SurfaceUpdates
import android.app.DownloadManager
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import android.os.Handler
import android.os.Looper
import android.view.ViewGroup
import android.webkit.URLUtil
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import com.chaquo.python.Python
import android.graphics.Color

/**
 * indiebizOS 런처 3표면(자율주행/수동/앱)을 폰 안에 띄우는 WebView.
 * 백엔드(127.0.0.1:8765)는 App 이 포그라운드 진입 시 기동하므로, 여기선 준비될 때까지
 * 기다렸다 로드한다(자동시작과의 race 방지). 소켓 바인드 지연은 onReceivedError 재시도로 흡수.
 */
class LauncherActivity : Activity() {
    private lateinit var surfaceUpdates: SurfaceUpdates
    private lateinit var web: WebView
    private val handler = Handler(Looper.getMainLooper())
    private var tries = 0

    /** <input type=file> 결과를 WebView 로 돌려줄 콜백 (공유창고 '파일 올리기' 등). */
    private var filePathCallback: ValueCallback<Array<Uri>>? = null

    private companion object { const val FILE_CHOOSER_REQUEST = 1001 }

    override fun onCreateOptionsMenu(menu: android.view.Menu): Boolean {
        if (!getSystemService(android.app.admin.DevicePolicyManager::class.java).isDeviceOwnerApp(packageName)) {
            return super.onCreateOptionsMenu(menu)
        }
        menu.add("업데이트 관리").setOnMenuItemClickListener {
            startActivity(Intent(this, com.indiebiz.phoneagent.update.UpdateManagementActivity::class.java))
            true
        }
        return true
    }

    @SuppressLint("SetJavaScriptEnabled")
    @Suppress("DEPRECATION")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // 시스템 홈·뒤로·최근 앱 버튼은 밝은 배경에 어두운 아이콘으로 표시한다.
        window.addFlags(android.view.WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS)
        window.navigationBarColor = Color.WHITE
        window.decorView.systemUiVisibility = window.decorView.systemUiVisibility or
            android.view.View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR

        surfaceUpdates = SurfaceUpdates(this, "phone", automatic = true)
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
                override fun onPageFinished(view: WebView, url: String?) { surfaceUpdates.pageReady() }
                // 런처 자신(127.0.0.1)만 WebView 안에서. 외부 사이트(즐겨찾기 등)는 시스템 브라우저로
                // → 런처 SPA 가 안 깨지고 뒤로가기도 정상(외부는 별도 앱).
                override fun shouldOverrideUrlLoading(view: WebView, req: WebResourceRequest): Boolean {
                    if (req.url.path == "/launcher/native-call") {
                        val source = Uri.parse(view.url ?: "")
                        val local = { uri: Uri -> uri.scheme == "http" && uri.host == "127.0.0.1" && uri.port == 8765 }
                        if (req.isForMainFrame && req.hasGesture() && local(source) && local(req.url)) {
                            val target = req.url.getQueryParameter("target") ?: ""
                            val purpose = req.url.getQueryParameter("purpose") ?: ""
                            if (target.matches(Regex("(npub1[023456789acdefghjklmnpqrstuvwxyz]{58}|[0-9a-fA-F]{64})")) &&
                                purpose in listOf("voice_call", "video_call")) {
                                startActivity(Intent(this@LauncherActivity, com.indiebiz.phoneagent.media.CallActivity::class.java)
                                    .putExtra("target", target).putExtra("purpose", purpose))
                            }
                        }
                        return true
                    }
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
            webChromeClient = object : WebChromeClient() {
                // ★기본 WebChromeClient 는 onShowFileChooser 가 false 를 돌려줘 <input type=file>
                // 이 **아무 반응도 하지 않는다**. 직접 구현해야 갤러리/파일 선택창이 뜬다
                // (공유창고 '파일 올리기' = 폰 사진을 집 창고로 넣는 경로).
                override fun onShowFileChooser(
                    webView: WebView,
                    callback: ValueCallback<Array<Uri>>,
                    params: FileChooserParams
                ): Boolean {
                    filePathCallback?.onReceiveValue(null)   // 앞선 요청이 남아 있으면 풀어준다
                    filePathCallback = callback
                    return try {
                        // createIntent() 가 HTML 의 accept/multiple 을 그대로 반영한다.
                        val intent = params.createIntent().addCategory(Intent.CATEGORY_OPENABLE)
                        startActivityForResult(intent, FILE_CHOOSER_REQUEST)
                        true
                    } catch (_: Exception) {
                        filePathCallback = null
                        false
                    }
                }
            }
            // ★WebView 는 DownloadListener 가 없으면 <a download> 를 **조용히 무시**한다
            // (onShowFileChooser 와 같은 부류). 공유창고 ⬇ 로 파일을 폰에 받으려면 필수.
            setDownloadListener { url, _, contentDisposition, mimeType, _ ->
                downloadToPhone(url, contentDisposition, mimeType)
            }
        }
        // 중앙의 세션 요청이 필요한 네이티브 화면을 준비한다. 런처에는 대기 버튼을 두지 않는다.
        surfaceUpdates.bind(web)
        setContentView(web)
        if (android.os.Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            val preferences = getSharedPreferences("media_setup", MODE_PRIVATE)
            if (!preferences.getBoolean("notification_asked", false)) {
                preferences.edit().putBoolean("notification_asked", true).apply()
                Toast.makeText(this, "수신 통화를 받으려면 알림을 허용해 주세요.", Toast.LENGTH_LONG).show()
                requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), 1002)
            }
        }
        loadWhenReady()
    }

    /** 창고 파일을 폰 공용 Download 폴더로 — [limbs:phone]{op:save} 와 같은 착지점. */
    private fun downloadToPhone(url: String, contentDisposition: String?, mimeType: String?) {
        try {
            val uri = Uri.parse(url)
            // 파일명: 우리 URL 은 ?name=<원본이름> 을 갖고 있어 한글이 온전하다. Content-Disposition
            // 의 ASCII 폴백(file.md)보다 낫다 — URLUtil 은 filename* (RFC 5987) 을 못 읽는다.
            val name = uri.getQueryParameter("name")?.substringAfterLast('/')
                ?: URLUtil.guessFileName(url, contentDisposition, mimeType)
            val req = DownloadManager.Request(uri).apply {
                setTitle(name)
                setMimeType(mimeType)
                setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, name)
            }
            (getSystemService(DOWNLOAD_SERVICE) as DownloadManager).enqueue(req)
            Toast.makeText(this, "받는 중: $name", Toast.LENGTH_SHORT).show()
        } catch (e: Exception) {
            Toast.makeText(this, "내려받기 실패: ${e.message}", Toast.LENGTH_LONG).show()
        }
    }

    @Deprecated("Activity 기반이라 registerForActivityResult 대신 클래식 경로를 쓴다")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        if (requestCode != FILE_CHOOSER_REQUEST) {
            @Suppress("DEPRECATION")
            super.onActivityResult(requestCode, resultCode, data)
            return
        }
        val cb = filePathCallback ?: return
        filePathCallback = null
        // ★취소해도 반드시 콜백을 돌려줘야 한다 — 안 그러면 그 <input> 이 영영 잠겨
        //   다시 눌러도 선택창이 안 뜬다(WebView 고전 함정).
        if (resultCode != RESULT_OK || data == null) {
            cb.onReceiveValue(null)
            return
        }
        val uris = mutableListOf<Uri>()
        val clip = data.clipData
        if (clip != null) {
            for (i in 0 until clip.itemCount) uris.add(clip.getItemAt(i).uri)   // 여러 장 선택
        } else {
            data.data?.let { uris.add(it) }
        }
        cb.onReceiveValue(if (uris.isEmpty()) null else uris.toTypedArray())
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
    override fun onDestroy() {
        surfaceUpdates.close()
        handler.removeCallbacksAndMessages(null)
        super.onDestroy()
    }
}
