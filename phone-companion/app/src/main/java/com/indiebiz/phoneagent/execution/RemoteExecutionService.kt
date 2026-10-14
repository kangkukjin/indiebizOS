package com.indiebiz.phoneagent.execution

import android.app.Service
import android.content.Intent
import android.os.*
import com.chaquo.python.Python
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import org.json.JSONObject

/** A private, disposable app-UID worker. Never starts the phone backend. */
class RemoteExecutionService : Service() {
    private val messenger = Messenger(Handler(Looper.getMainLooper()) { message ->
        if (message.what == 1) {
            val parent = message.replyTo
            RemoteWorkerContext.parent = parent
            parent.send(Message.obtain(null, 10, Process.myPid(), 0))
            val request = message.data.getString("request")!!
            Thread {
                try {
                    val result = Python.getInstance().getModule("phone_exec_worker").callAttr("run", request).toString()
                    parent.send(Message.obtain(null, 2).apply { data = Bundle().apply { putString("result", result) } })
                } catch (error: Throwable) {
                    parent.send(Message.obtain(null, 3).apply {
                        data = Bundle().apply { putString("error", error.toString()) }
                    })
                }
            }.start()
            true
        } else false
    })

    override fun onCreate() { super.onCreate(); RemoteWorkerContext.context = applicationContext }
    override fun onBind(intent: Intent): IBinder = messenger.binder
    override fun onDestroy() {
        // If the parent dies, Android unbinds the private service. Do not leave Python alive.
        super.onDestroy()
        val pid = Process.myPid()
        WorkerProcessTree.terminate(pid, WorkerProcessTree.info(pid)?.second, allowSelf = true)
        Process.killProcess(pid)
    }
}

/** Worker-to-main resource calls: service-owned state stays in its owning process. */
object RemoteWorkerContext {
    lateinit var context: android.content.Context
    lateinit var parent: Messenger
    private val sequence = AtomicInteger()
    private data class Pending(val done: CountDownLatch = CountDownLatch(1), var reply: String = "")
    private val pending = ConcurrentHashMap<Int, Pending>()
    private val receiver = Messenger(Handler(Looper.getMainLooper()) { message ->
        pending[message.arg1]?.let { it.reply = message.data.getString("result_path") ?: ""; it.done.countDown() }
        true
    })
    @JvmStatic fun applicationContext(): android.content.Context = context
    @JvmStatic fun call(method: String, args: String): String {
        check(Looper.myLooper() != Looper.getMainLooper()) { "device_call_on_main_thread" }
        require(args.toByteArray(Charsets.UTF_8).size <= 65536) { "device_call_too_large" }
        val id = sequence.incrementAndGet()
        val call = Pending()
        pending[id] = call
        try {
            parent.send(Message.obtain(null, 20, id, 0).apply {
                replyTo = receiver
                data = Bundle().apply { putString("method", method); putString("args", args) }
            })
            check(call.done.await(310, TimeUnit.SECONDS)) { "device_call_timeout" }
            return File(call.reply).readText()
        } finally { pending.remove(id) }
    }
}
