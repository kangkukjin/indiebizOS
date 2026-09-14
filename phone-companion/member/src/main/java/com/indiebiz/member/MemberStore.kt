package com.indiebiz.member

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

/** 봉투와 로컬 상태만 유지한다. IBL은 해석하지 않는다. */
class MemberStore(context: Context) {
    val root = File(context.filesDir, "member").apply { mkdirs() }
    val db = SQLiteDatabase.openOrCreateDatabase(File(root, "member.db"), null)
    init {
        db.enableWriteAheadLogging()
        db.execSQL("PRAGMA synchronous=FULL")
        db.execSQL("CREATE TABLE IF NOT EXISTS jobs(key TEXT PRIMARY KEY,fingerprint TEXT,state TEXT,result TEXT,updated INTEGER)")
        db.execSQL("CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,user TEXT,assistant TEXT,created INTEGER)")
        db.execSQL("CREATE TABLE IF NOT EXISTS episodes(id TEXT PRIMARY KEY,data TEXT)")
        db.execSQL("CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY,content TEXT)")
        db.execSQL("CREATE TABLE IF NOT EXISTS scripts(id TEXT PRIMARY KEY,path TEXT,interpreter TEXT,description TEXT,resources TEXT,dependencies TEXT)")
        db.execSQL("CREATE TABLE IF NOT EXISTS sentences(id TEXT PRIMARY KEY,code TEXT)")
        db.execSQL("CREATE TABLE IF NOT EXISTS hippocampus_examples(id TEXT PRIMARY KEY,data TEXT)")
        db.execSQL("CREATE TABLE IF NOT EXISTS forage(id TEXT PRIMARY KEY,data TEXT)")
        db.execSQL("UPDATE jobs SET state='unknown' WHERE state='running'")
    }
    @Synchronized fun claim(key: String, raw: String): JSONObject? {
        val fp = MessageDigest.getInstance("SHA-256").digest(raw.toByteArray()).joinToString("") { "%02x".format(it) }
        db.rawQuery("SELECT fingerprint,state,result FROM jobs WHERE key=?", arrayOf(key)).use {
            if (it.moveToFirst()) {
                if (it.getString(0) != fp) return error("key_conflict")
                if (it.getString(1) != "received") return result(key)
                return null
            }
        }
        db.execSQL("INSERT INTO jobs VALUES(?,?,'received',NULL,?)", arrayOf(key, fp, System.currentTimeMillis()))
        return null
    }
    fun running(key: String) { db.execSQL("UPDATE jobs SET state='running' WHERE key=?", arrayOf(key)) }
    fun complete(key: String, result: JSONObject) {
        db.execSQL("UPDATE jobs SET state='completed',result=?,updated=? WHERE key=?", arrayOf(result.toString(),System.currentTimeMillis(),key))
    }
    fun result(key: String): JSONObject {
        db.rawQuery("SELECT state,result FROM jobs WHERE key=?", arrayOf(key)).use {
            if (!it.moveToFirst()) return error("not_found")
            val state = it.getString(0)
            return JSONObject(it.getString(1) ?: "{}").put("state",state).put("request_key",key).apply {
                if (state != "completed") { put("success",false); put("error","result_"+state) }
            }
        }
    }
    fun results(): JSONArray {
        val out = JSONArray()
        db.rawQuery("SELECT key,state,result FROM jobs WHERE state IN ('completed','unknown') ORDER BY updated DESC LIMIT 40",null).use {
            while(it.moveToNext()) out.put(JSONObject().put("key",it.getString(0)).put("state",it.getString(1)).put("result",JSONObject(it.getString(2) ?: "{}")))
        }
        return out
    }
    fun save(r: JSONObject): JSONObject {
        val id = r.optString("id")
        if (id.isEmpty()) return error("id_required")
        db.beginTransaction()
        try {
            if (r.has("content")) db.execSQL("INSERT OR REPLACE INTO memories VALUES(?,?)",arrayOf(id,r.getString("content")))
            else {
                db.execSQL("INSERT OR IGNORE INTO conversations(id,user,assistant,created) VALUES(?,?,?,?)",arrayOf(id,r.optString("user"),r.optString("assistant"),System.currentTimeMillis()/1000))
                db.execSQL("INSERT OR IGNORE INTO episodes VALUES(?,?)",arrayOf(id,r.optJSONObject("episode")?.toString() ?: "{}"))
            }
            db.setTransactionSuccessful()
        } finally { db.endTransaction() }
        return JSONObject().put("success",true).put("saved",true).put("id",id)
    }
    fun recall(q: String): JSONObject {
        val history = JSONArray(); val memories = JSONArray(); val sentences = JSONArray()
        db.rawQuery("SELECT user,assistant FROM (SELECT rowid,user,assistant FROM conversations ORDER BY rowid DESC LIMIT 40) ORDER BY rowid",null).use {
            while(it.moveToNext()) { history.put(JSONObject().put("role","user").put("content",it.getString(0))); history.put(JSONObject().put("role","assistant").put("content",it.getString(1))) }
        }
        db.rawQuery("SELECT id,content FROM memories WHERE instr(content,?)>0 OR ?='' LIMIT 40",arrayOf(q,q)).use {
            while(it.moveToNext()) memories.put(JSONObject().put("id",it.getString(0)).put("content",it.getString(1)))
        }
        db.rawQuery("SELECT id,code FROM sentences ORDER BY id LIMIT 100",null).use {
            while(it.moveToNext()) sentences.put(JSONObject().put("id",it.getString(0)).put("code",it.getString(1)))
        }
        return JSONObject().put("success",true).put("history",history).put("memories",memories).put("sentences",sentences).put("recent_results",results())
    }
    fun path(raw: String): File {
        val files = File(root,"files").apply { mkdirs() }.canonicalFile
        val p = if(File(raw).isAbsolute) File(raw).canonicalFile else File(files,raw).canonicalFile
        require(p == files || p.path.startsWith(files.path+File.separator)) { "회원 저장소 밖 경로" }
        return p
    }
    fun export(): JSONObject {
        val file = File(root,"member-export-${System.currentTimeMillis()}.zip")
        db.beginTransaction()
        try {
            ZipOutputStream(file.outputStream()).use { z ->
                val tables = JSONObject()
                for(t in listOf("conversations","episodes","memories","scripts","sentences","hippocampus_examples","forage","tasks","task_events")) {
                    val rows = JSONArray()
                    db.rawQuery("SELECT * FROM "+t,null).use { c ->
                        while(c.moveToNext()) {
                            val r = JSONObject()
                            for(i in 0 until c.columnCount) r.put(c.getColumnName(i),if(c.isNull(i)) JSONObject.NULL else c.getString(i))
                            rows.put(r)
                        }
                    }; tables.put(t,rows)
                }
                z.putNextEntry(ZipEntry("manifest.json"))
                z.write(JSONObject().put("format","indiebiz-member").put("version",1).put("tables",tables).toString().toByteArray())
                z.closeEntry()
            }
            db.setTransactionSuccessful()
        } finally { db.endTransaction() }
        return JSONObject().put("success",true).put("path",file.path)
    }
    companion object { fun error(s: String) = JSONObject().put("success",false).put("error",s) }
}
