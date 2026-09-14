package com.indiebiz.member

import android.content.Context
import android.content.Intent
import android.hardware.*
import android.media.MediaPlayer
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.util.AtomicFile
import android.util.Base64
import com.indiebiz.phoneagent.PhoneAccessibilityService
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.*
import java.io.File

class MemberRuntime(val context: Context) {
    val store = MemberStore(context)
    val prefs = context.getSharedPreferences("member",Context.MODE_PRIVATE)
    val workers = Executors.newFixedThreadPool(4)
    val approvals = ConcurrentHashMap<String,Pair<JSONObject,CompletableFuture<Boolean>>>()
    val client = OkHttpClient.Builder().readTimeout(240,TimeUnit.SECONDS).build()
    @Volatile var active = false
    @Volatile var session = ""
    @Volatile var status = "연결 대기"
    private var player: MediaPlayer? = null
    fun base() = prefs.getString("base","")!!.trimEnd('/')
    fun key() = MemberKeyStore.read(context)
    fun post(path: String, body: JSONObject): JSONObject {
        require(Uri.parse(base()).scheme == "https") { "HTTPS 허브 주소가 필요합니다" }
        val request = Request.Builder().url(base()+path).post(body.toString().toRequestBody("application/json".toMediaType())).build()
        client.newCall(request).execute().use { r -> check(r.isSuccessful) { "허브 응답 ${r.code}" }; return JSONObject(r.body!!.string()) }
    }
    fun html(): String {
        // 로컬 승인 UI를 허브가 바꿀 수 없도록 공통 소스의 빌드 번들을 사용한다.
        return context.assets.open("member_app.html").bufferedReader().use { it.readText() }
    }
    fun connectLoop() {
        if(active) return
        active = true
        workers.execute {
            while(active) try {
                val hello = post("/limb/connect",JSONObject().put("key",key()).put("mode","member").put("host","Android 회원")
                    .put("env",JSONObject().put("os","android").put("mode","member")))
                check(hello.optBoolean("success")) { hello.optString("error") }
                session = hello.getString("session"); status = "연결됨"
                while(active) {
                    val poll = post("/limb/poll",JSONObject().put("key",key()).put("session",session).put("wait",25))
                    check(poll.optBoolean("success")) { poll.optString("error") }
                    if(poll.optBoolean("stale")) { active=false; status="다른 기기에서 연결됨"; break }
                    val jobs = poll.optJSONArray("jobs") ?: JSONArray()
                    for(i in 0 until jobs.length()) {
                        if(!active) break
                        val job=jobs.getJSONObject(i)
                        val result = run(job.getString("code"))
                        // 실패하면 같은 작업의 결과만 재전송한다. 실행 함수를 다시 부르지 않는다.
                        for(attempt in 0..2) try {
                            val receipt=post("/limb/result",JSONObject().put("key",key()).put("job_id",job.getString("id")).put("result",result))
                            check(receipt.optBoolean("success")); break
                        } catch(e:Exception) { if(attempt<2) Thread.sleep(1000) }
                    }
                }
            } catch(e:Exception) { status="연결 대기 · 로컬 결과는 보존됨"; if(active) Thread.sleep(2000) }
        }
    }
    @Synchronized fun run(raw: String): JSONObject {
        val c = try { JSONObject(raw) } catch(e:Exception) { return MemberStore.error("bad_command") }
        val key=c.optString("request_key")
        if(!c.optBoolean("member") || key.isEmpty()) return MemberStore.error("member_envelope_required")
        if(c.optString("op")=="result_query") return store.result(c.optString("query_key"))
        store.claim(key,raw)?.let { return it }
        val out = try {
            if(!approve(c)) MemberStore.error("permission_denied")
            else { store.running(key); execute(c) }
        } catch(e:Exception) { MemberStore.error(e.message ?: "execution_failed") }
        out.put("request_key",key)
        try { store.complete(key,out) } catch(e:Exception) { return MemberStore.error("result_unknown") }
        return out
    }
    fun approve(c:JSONObject):Boolean {
        val op=c.optString("op")
        if(op in listOf("read","list","info","memory_recall","script_list")) return true
        if(op=="memory_save" && c.optJSONObject("record")?.has("user")==true) return true
        val key=c.getString("request_key"); val answer=CompletableFuture<Boolean>()
        approvals[key]=Pair(c,answer)
        return try { answer.get(120,TimeUnit.SECONDS) } catch(e:Exception) { false } finally { approvals.remove(key) }
    }
    fun execute(c:JSONObject):JSONObject {
        return when(c.optString("op")) {
            "memory_save" -> store.save(c.getJSONObject("record"))
            "memory_recall" -> store.recall(c.optString("query"))
            "read" -> { val f=store.path(c.getString("path")); require(f.length()<=32*1024*1024)
                JSONObject().put("success",true).put("content",if(c.optString("encoding")=="base64") Base64.encodeToString(f.readBytes(),Base64.NO_WRAP) else f.readText()) }
            "write" -> { val f=store.path(c.getString("path")); f.parentFile!!.mkdirs()
                val af=AtomicFile(f); val stream=af.startWrite()
                try { stream.write(if(c.optString("encoding")=="base64") Base64.decode(c.optString("content"),Base64.DEFAULT) else c.optString("content").toByteArray()); af.finishWrite(stream) }
                catch(e:Exception) { af.failWrite(stream); throw e }
                JSONObject().put("success",true).put("saved",true).put("path",f.path) }
            "list" -> { val rows=JSONArray(); store.path(c.optString("path")).listFiles()?.forEach { rows.put(JSONObject().put("name",it.name).put("path",it.path).put("type",if(it.isDirectory)"directory" else "file")) }; JSONObject().put("success",true).put("items",rows) }
            "mkdir" -> { val f=store.path(c.getString("path")); check(f.isDirectory || f.mkdirs()); JSONObject().put("success",true).put("path",f.path) }
            "file_move" -> { val f=store.path(c.getString("path")); val dest=store.path(c.getString("dest")); require(!dest.exists()); check(f.renameTo(dest)); JSONObject().put("success",true).put("path",dest.path) }
            "info" -> JSONObject().put("success",true).put("os","android").put("storage",store.path("").path)
            "export" -> store.export()
            "script_list" -> JSONObject().put("success",true).put("items",JSONArray())
            "script" -> if(c.optString("action") in listOf("","list")) JSONObject().put("success",true).put("items",JSONArray()) else MemberStore.error("폰 회원 모드에는 프로그램 인터프리터가 없습니다")
            "play" -> play(c.optString("url",c.optString("path")))
            "open" -> { val u=Uri.parse(c.getString("url")); require(u.scheme in listOf("http","https")); context.startActivity(Intent(Intent.ACTION_VIEW,u).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)); JSONObject().put("success",true) }
            "sensor" -> sensor()
            "accessibility" -> accessibility(c)
            else -> MemberStore.error("unsupported_op")
        }
    }
    fun play(url:String):JSONObject {
        val uri=Uri.parse(url)
        val p=MediaPlayer()
        if(uri.scheme in listOf("http","https")) p.setDataSource(url) else p.setDataSource(store.path(url).path)
        player?.release(); player=p
        p.prepare(); p.start()
        return JSONObject().put("success",true).put("playing",true)
    }
    fun sensor():JSONObject {
        val manager=context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
        val sensor=manager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER) ?: return MemberStore.error("sensor_unavailable")
        val latch=CountDownLatch(1); var values=floatArrayOf()
        val listener=object:SensorEventListener {
            override fun onAccuracyChanged(s:Sensor?,a:Int) {}
            override fun onSensorChanged(e:SensorEvent) { values=e.values.clone(); latch.countDown() }
        }
        manager.registerListener(listener,sensor,SensorManager.SENSOR_DELAY_NORMAL,Handler(Looper.getMainLooper()))
        try { if(!latch.await(5,TimeUnit.SECONDS)) return MemberStore.error("sensor_timeout") }
        finally { manager.unregisterListener(listener) }
        return JSONObject().put("success",true).put("type","accelerometer").put("values",JSONArray(values.toList()))
    }
    fun accessibility(c:JSONObject):JSONObject = JSONObject(when(c.optString("action")) {
        "snapshot" -> PhoneAccessibilityService.snapshot()
        "tap" -> PhoneAccessibilityService.tap(c.getInt("x"),c.getInt("y"))
        "type" -> PhoneAccessibilityService.typeText(c.getString("text"))
        "swipe" -> PhoneAccessibilityService.swipeDir(c.getString("direction"))
        "key" -> PhoneAccessibilityService.pressKey(c.getString("key"))
        else -> """{"success":false,"error":"unsupported_action"}"""
    })
    fun local(path:String,body:JSONObject):Any = when(path) {
        "history" -> store.recall("")
        "results" -> store.results()
        "approvals" -> JSONArray(approvals.map { (k,v) -> JSONObject().put("key",k).put("command",v.first) })
        "approve" -> JSONObject().put("success",approvals[body.optString("key")]?.second?.complete(body.optBoolean("allow")) ?: false)
        "export" -> store.export()
        "chat","profile","close" -> post(when(path) { "chat" -> "/m/chat"; "profile" -> "/m/profile"; else -> "/m/session/close" },JSONObject().put("key",key()).apply { if(path=="chat")put("message",body.optString("message")) })
        else -> MemberStore.error("route_not_found")
    }
    companion object {
        @Volatile private var singleton:MemberRuntime?=null
        @Synchronized fun get(c:Context):MemberRuntime = singleton ?: MemberRuntime(c.applicationContext).also { singleton=it }
    }
}
