package com.indiebiz.member

import org.json.JSONArray
import org.json.JSONObject
import okhttp3.Request
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.UUID
import java.util.concurrent.TimeUnit

/** 작업과 진행 기록의 정본은 회원 기기의 SQLite다. 허브 응답을 재실행하지 않는다. */
class MemberTasks(private val runtime: MemberRuntime) {
    private val store = runtime.store
    private val db = store.db
    @Volatile private var running = ""
    init {
        db.execSQL("CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,title TEXT,workspace TEXT,state TEXT,result TEXT,created INTEGER,updated INTEGER)")
        db.execSQL("CREATE TABLE IF NOT EXISTS task_events(id INTEGER PRIMARY KEY AUTOINCREMENT,task_id TEXT,kind TEXT,content TEXT)")
        db.execSQL("UPDATE tasks SET state='unknown' WHERE state='running'")
        val columns = mutableSetOf<String>()
        db.rawQuery("PRAGMA table_info(conversations)", null).use { while(it.moveToNext()) columns.add(it.getString(1)) }
        if("task_id" !in columns) db.execSQL("ALTER TABLE conversations ADD COLUMN task_id TEXT NOT NULL DEFAULT ''")
    }
    fun workspace() = JSONObject().put("success",true).put("workspace",store.path("").path).put("fixed",true)
    fun list(): JSONArray {
        val rows=JSONArray()
        db.rawQuery("SELECT id,title,workspace,state FROM tasks ORDER BY updated DESC LIMIT 100",null).use {
            while(it.moveToNext()) rows.put(JSONObject().put("id",it.getString(0)).put("title",it.getString(1)).put("workspace",it.getString(2)).put("state",it.getString(3)))
        }
        return rows
    }
    fun get(id:String):JSONObject {
        val task=JSONObject().put("success",true)
        db.rawQuery("SELECT title,workspace,state,result FROM tasks WHERE id=?",arrayOf(id)).use {
            if(!it.moveToFirst()) return MemberStore.error("task_not_found")
            task.put("id",id).put("title",it.getString(0)).put("workspace",it.getString(1)).put("state",it.getString(2)).put("result",JSONObject(it.getString(3) ?: "{}"))
        }
        val events=JSONArray()
        db.rawQuery("SELECT kind,content FROM (SELECT id,kind,content FROM task_events WHERE task_id=? ORDER BY id DESC LIMIT 500) ORDER BY id",arrayOf(id)).use {
            while(it.moveToNext()) events.put(JSONObject().put("kind",it.getString(0)).put("value",JSONArray(it.getString(1)).opt(0)))
        }
        return task.put("events",events)
    }
    private fun event(id:String,kind:String,value:Any?) {
        db.execSQL("INSERT INTO task_events(task_id,kind,content) VALUES(?,?,?)",arrayOf(id,kind,JSONArray().put(value ?: JSONObject.NULL).toString()))
    }
    @Synchronized fun start(body:JSONObject):JSONObject {
        if(running.isNotEmpty()) return MemberStore.error("진행 중인 작업을 완료하거나 중단하세요")
        val message=body.optString("message"); val code=body.optString("code")
        if(message.isBlank() && code.isBlank()) return MemberStore.error("요청을 입력하세요")
        var id=body.optString("task_id")
        val now=System.currentTimeMillis()
        if(id.isEmpty()) {
            id=UUID.randomUUID().toString()
            db.execSQL("INSERT INTO tasks VALUES(?,?,?,'idle','{}',?,?)",arrayOf(id,message.take(60),store.path("").path,now,now))
        } else if(!get(id).optBoolean("success")) return MemberStore.error("task_not_found")
        running=id
        db.execSQL("UPDATE tasks SET state='running',updated=? WHERE id=?",arrayOf(now,id))
        event(id,"user",message)
        runtime.workers.execute { run(id,message,code) }
        return JSONObject().put("success",true).put("queued",true).put("task_id",id)
    }
    private fun run(id:String,message:String,code:String) {
        var result=MemberStore.error("연결이 끊겼습니다. 실행 결과를 확인하세요")
        var state="unknown"
        try {
            val body=JSONObject().put("key",runtime.key()).put("task_id",id).put("message",message)
            if(code.isNotEmpty()) body.put("code",code)
            require(android.net.Uri.parse(runtime.base()).scheme=="https")
            val request=Request.Builder().url(runtime.base()+"/m/run").post(body.toString().toRequestBody("application/json".toMediaType())).build()
            runtime.client.newBuilder().readTimeout(35,TimeUnit.MINUTES).build().newCall(request).execute().use { response ->
                if(!response.isSuccessful) { result=MemberStore.error("허브 응답 ${response.code}"); state="failed" }
                else response.body!!.charStream().buffered().useLines { lines ->
                    lines.forEach { line ->
                        if(line.isNotBlank()) {
                            val item=JSONObject(line)
                            when(item.optString("type")) {
                                "event" -> event(id,"progress",item.optJSONObject("event"))
                                "result" -> { result=item.getJSONObject("result"); state=if(result.optBoolean("success")) "completed" else "failed" }
                            }
                        }
                    }
                }
            }
        } catch(e:Exception) { if(state!="completed" && state!="failed") result=MemberStore.error(e.message ?: "result_unknown") }
        finally {
            event(id,"assistant",result.optString("response",result.optString("error")))
            db.execSQL("UPDATE tasks SET state=?,result=?,updated=? WHERE id=?",arrayOf(state,result.toString(),System.currentTimeMillis(),id))
            running=""
        }
    }
    fun recall(c:JSONObject):JSONObject {
        val out=store.recall(c.optString("query"))
        val id=c.optString("task_id")
        if(id.isEmpty()) return out
        require(get(id).optBoolean("success")) { "task_not_found" }
        val history=JSONArray()
        db.rawQuery("SELECT user,assistant FROM (SELECT rowid,user,assistant FROM conversations WHERE task_id=? ORDER BY rowid DESC LIMIT 40) ORDER BY rowid",arrayOf(id)).use {
            while(it.moveToNext()) { history.put(JSONObject().put("role","user").put("content",it.getString(0))); history.put(JSONObject().put("role","assistant").put("content",it.getString(1))) }
        }
        return out.put("history",history).put("workspace",store.path("").path).put("shell_available",false)
    }
    fun save(c:JSONObject):JSONObject {
        val record=c.getJSONObject("record")
        val result=store.save(record)
        if(c.optString("task_id").isNotEmpty() && result.optBoolean("success")) db.execSQL("UPDATE conversations SET task_id=? WHERE id=?",arrayOf(c.getString("task_id"),record.getString("id")))
        return result
    }
}
