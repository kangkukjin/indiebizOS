package com.indiebiz.ui

import android.app.Activity
import android.app.AlertDialog
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.util.AtomicFile
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.widget.Button
import android.widget.Toast
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.io.File
import java.util.UUID
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/** One UI release contract for both Android shells; never touches the executor or its data. */
class SurfaceUpdates(private val activity: Activity, private val surface: String) {
    private val main = Handler(Looper.getMainLooper())
    private val worker = Executors.newSingleThreadExecutor()
    private val directory = File(activity.filesDir, "ui-releases").apply { mkdirs() }
    private val stateFile = AtomicFile(File(directory, "state.json"))
    private var storageHealthy = true
    private var state = readState()
    private val trust = try { JSONObject(activity.assets.open("surface-update-trust.json").bufferedReader().readText()) } catch (_: Exception) { JSONObject() }
    private val verifier=SurfaceReleaseVerifier(trust,surface)
    private val client = OkHttpClient.Builder().followRedirects(false).followSslRedirects(false)
        .connectTimeout(30, TimeUnit.SECONDS).readTimeout(120, TimeUnit.SECONDS).build()
    private var web: WebView? = null
    private var nonce = ""
    private var completion: ((Boolean, String) -> Unit)? = null
    private var busy = false
    private var closed = false
    private var offered: JSONObject? = null
    private val configured get() = trust.optString("feed").isNotEmpty() && trust.optString("publicKey").isNotEmpty()
    val button = Button(activity).apply {
        text = "화면 업데이트"
        setOnClickListener { if (!busy) check(true) }
    }

    init {
        // A process death before renderer acknowledgement retains the previous confirmed UI.
        if (state.has("pending")) {
            state.remove("pending")
            try { writeState() } catch (_: Exception) { storageHealthy=false }
        }
    }
    private fun readState(): JSONObject = try {
        JSONObject(stateFile.openRead().bufferedReader().use { it.readText() })
    } catch (_: java.io.FileNotFoundException) { JSONObject().put("active", 0).put("highest", 0) }
    catch (_: Exception) { storageHealthy=false; JSONObject().put("active",0).put("highest",0) }
    private fun writeState() {
        val stream = stateFile.startWrite()
        try { stream.write(state.toString().toByteArray()); stateFile.finishWrite(stream) }
        catch (error: Exception) { stateFile.failWrite(stream); throw error }
    }
    private fun fetch(url: String, limit: Int): ByteArray {
        require(verifier.origin(url) == verifier.origin(trust.getString("feed"))) { "배포 경로가 다릅니다" }
        client.newCall(Request.Builder().url(url).build()).execute().use { response ->
            require(response.isSuccessful) { "업데이트를 내려받지 못했습니다" }
            val body = response.body ?: error("응답이 비어 있습니다")
            require(body.contentLength() <= limit) { "업데이트 크기 초과" }
            body.byteStream().use { input ->
                val output = java.io.ByteArrayOutputStream()
                val buffer = ByteArray(8192)
                while (true) {
                    val count = input.read(buffer); if (count < 0) break
                    require(output.size() + count <= limit) { "업데이트 크기 초과" }
                    output.write(buffer, 0, count)
                }
                return output.toByteArray()
            }
        }
    }
    private fun load(sequence: Long): JSONObject {
        val release = File(directory, sequence.toString())
        val envelope = JSONObject(File(release, "manifest.json").readText())
        val manifest = verifier.verify(envelope, true)
        require(manifest.getLong("sequence") == sequence) { "화면 판본 불일치" }
        return verifier.payload(manifest, File(release, "display.json").readBytes())
    }
    fun bind(view: WebView) {
        web = view
        view.addJavascriptInterface(object {
            @JavascriptInterface fun done(token: String, success: Boolean, message: String) {
                main.post {
                    if (!closed && token == nonce && nonce.isNotEmpty()) {
                        nonce = ""; val callback = completion; completion = null; callback?.invoke(success, message.take(500))
                    }
                }
            }
        }, "IndieSurfaceResult")
        main.postDelayed({ if (!closed) check(false) }, 15000)
    }
    private fun apply(display: JSONObject, callback: (Boolean, String) -> Unit) {
        val value = display.toString().replace("<", "\\u003c")
        evaluate("Promise.resolve(window.__indieInitialDisplay).then(()=>window.IndieDisplay.current().version===$value.version?{}:window.IndieDisplay.apply($value))",callback)
    }
    private fun evaluate(expression: String, callback: (Boolean, String) -> Unit) {
        val view = web ?: error("화면이 열리지 않았습니다")
        nonce = UUID.randomUUID().toString(); completion = callback
        val token = JSONObject.quote(nonce)
        view.evaluateJavascript("$expression.then(()=>IndieSurfaceResult.done($token,true,''),e=>IndieSurfaceResult.done($token,false,String(e.message||e)))", null)
    }
    fun pageReady() {
        val active = state.optLong("active")
        if (active <= 0 || busy || closed) return
        busy = true
        worker.execute {
            try { val value = load(active); main.post { if (!closed) apply(value) { ok, message ->
                busy = false
                if (!ok) { state.put("active",0); try { writeState() } catch (_: Exception) { storageHealthy=false }; notice("APK 기본 화면 유지 · $message") }
            } } }
            catch (error: Exception) { main.post { busy = false; notice("기본 화면 유지 · ${error.message}") } }
        }
    }
    private fun check(prompt: Boolean) {
        if (closed || busy) return
        if (!storageHealthy) { if(prompt) notice("화면 저장소 복구가 필요합니다. 기본 화면을 유지합니다"); return }
        if (!configured) { if (prompt) notice("이 설치물에는 화면 업데이트 채널이 설정되지 않았습니다"); return }
        busy = true
        worker.execute {
            try {
                val envelope = JSONObject(String(fetch(trust.getString("feed"),131072),Charsets.UTF_8))
                val manifest = verifier.verify(envelope)
                main.post {
                    busy = false;if (closed) return@post
                    offered = if (manifest.getLong("sequence") > state.optLong("highest")) envelope else null
                    button.text = if (offered == null) "화면 업데이트" else "새 화면 있음"
                    if (prompt && offered != null) AlertDialog.Builder(activity).setMessage("새 화면 ${manifest.getString("version")}을 적용할까요? 작성 중인 내용과 작업은 유지됩니다.")
                        .setNegativeButton("취소",null).setPositiveButton("설치") { _,_ -> install(envelope) }.show()
                    else if (prompt) notice("최신 화면입니다")
                }
            } catch (error: Exception) { main.post { busy = false;if(prompt)notice(error.message ?: "업데이트 확인 실패") } }
        }
    }
    private fun install(envelope: JSONObject) {
        if (busy || closed) return
        busy = true;button.isEnabled=false
        worker.execute {
            try {
                val manifest = verifier.verify(envelope);val sequence = manifest.getLong("sequence")
                require(sequence > state.optLong("highest")) { "이미 적용한 판본입니다" }
                val file = manifest.getJSONArray("files").getJSONObject(0)
                val bytes = fetch(file.getString("url"),file.getInt("size"));val display = verifier.payload(manifest,bytes)
                val release = File(directory,sequence.toString())
                if (release.exists()) {
                    require(File(release,"manifest.json").readText()==envelope.toString()) { "같은 순번의 다른 판본입니다" }
                    verifier.payload(manifest,File(release,"display.json").readBytes())
                } else {
                    val stage=File(directory,".candidate-${UUID.randomUUID()}").apply { mkdirs() }
                    try {
                        java.io.FileOutputStream(File(stage,"display.json")).use { it.write(bytes);it.fd.sync() }
                        java.io.FileOutputStream(File(stage,"manifest.json")).use { it.write(envelope.toString().toByteArray());it.fd.sync() }
                        require(stage.renameTo(release)) { "판본 저장 실패" }
                    } finally { stage.deleteRecursively() }
                }
                main.post {
                    if (closed) return@post
                    val previous=JSONObject(state.toString())
                    try {
                        state.put("pending",sequence);writeState()
                        apply(display) { ok,message ->
                            try {
                                state=JSONObject(previous.toString())
                                if (ok) state.put("active",sequence).put("highest",sequence)
                                writeState();busy=false;button.isEnabled=true
                                if(ok){offered=null;button.text="화면 업데이트"}else notice("이전 화면 유지 · $message")
                            } catch (error: Exception) {
                                state=previous;storageHealthy=false
                                if (ok) evaluate("window.IndieDisplay.rollback(${JSONObject.quote(display.getString("version"))})") { _,_ -> busy=false;button.isEnabled=true;notice("저장 실패 · 이전 화면 복구") }
                                else {busy=false;button.isEnabled=true;notice("이전 화면 유지 · 저장소 복구 필요")}
                            }
                        }
                    } catch (error: Exception) { state=previous;busy=false;button.isEnabled=true;notice("이전 화면 유지 · ${error.message}") }
                }
            } catch (error: Exception) { main.post { busy=false;button.isEnabled=true;notice(error.message ?: "설치 실패") } }
        }
    }
    private fun notice(message: String) { if (!closed) Toast.makeText(activity,message,Toast.LENGTH_LONG).show() }
    fun close() { closed=true;nonce="";completion=null;main.removeCallbacksAndMessages(null);web?.removeJavascriptInterface("IndieSurfaceResult");web=null;worker.shutdownNow() }

    companion object {
        @JvmStatic fun withActive(context: Context, surface: String, html: String): String {
            return try {
                val root=File(context.filesDir,"ui-releases")
                val state=JSONObject(AtomicFile(File(root,"state.json")).openRead().bufferedReader().use { it.readText() })
                val active=state.optLong("active");if(active<=0)return html
                val trust=JSONObject(context.assets.open("surface-update-trust.json").bufferedReader().use { it.readText() })
                val verifier=SurfaceReleaseVerifier(trust,surface)
                val directory=File(root,active.toString())
                val manifest=verifier.verify(JSONObject(File(directory,"manifest.json").readText()),true)
                require(manifest.getLong("sequence")==active)
                val value=verifier.payload(manifest,File(directory,"display.json").readBytes()).toString().replace("<","\\u003c")
                val script="<script>window.__indieInitialDisplay=Promise.resolve().then(()=>window.IndieDisplay.current().host===$value.host?window.IndieDisplay.apply($value):null);</script>"
                html.replace("<!--INDIE_ACTIVE_DISPLAY-->",script)
            } catch (_: Exception) { html } // Verified APK baseline is always available, including offline.
        }
    }
}
