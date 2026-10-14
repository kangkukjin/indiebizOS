package com.indiebiz.phoneagent.execution

import android.content.*
import android.os.*
import com.indiebiz.phoneagent.BaseBundle
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** Parent owns deadlines, cancellation, worker death, and durable result files. */
object RemoteExecutionBridge {
    private lateinit var context: Context
    private val main = Handler(Looper.getMainLooper())
    private val active = ConcurrentHashMap<String, Job>()
    private val serial = java.util.concurrent.locks.ReentrantLock()
    private class Job {
        val done = CountDownLatch(1)
        @Volatile var cancelled = false
        @Volatile var pid = 0
        @Volatile var birth: String? = null
        @Volatile var result: String? = null
        @Volatile var error: String? = null
        val calls = ConcurrentHashMap.newKeySet<Thread>()
    }

    @JvmStatic fun init(ctx: Context) { context = ctx.applicationContext }
    @JvmStatic fun capabilities(): String {
        if (!::context.isInitialized) return "{}"
        val runtime = JSONObject().put("identity", "app").put("ready", true).put("timeout_default", 120).put("timeout_max", 3600)
            .put("cwd", File(context.filesDir, "userdata/remote_work").absolutePath)
        return JSONObject().put("execution_contract", 1).put("shell", true)
            .put("runtimes", JSONObject()
                .put("shell", JSONObject(runtime.toString()).put("executable", "/system/bin/sh"))
                .put("python", JSONObject(runtime.toString()).put("implementation", "chaquopy").put("bridge_version", 1)))
            .put("abi", Build.SUPPORTED_ABIS.firstOrNull()).put("sdk", Build.VERSION.SDK_INT).put("target_sdk", context.applicationInfo.targetSdkVersion)
            .put("uid", Process.myUid()).put("observed_at", System.currentTimeMillis() / 1000.0).toString()
    }

    @JvmStatic fun cancel(id: String): Boolean {
        val job = active[id] ?: return false
        job.cancelled = true
        job.done.countDown()
        return true
    }

    @JvmStatic fun execute(id: String, code: String): String {
        check(::context.isInitialized) { "execution_bridge_unavailable" }
        check(id.matches(Regex("[A-Za-z0-9_-]{1,128}"))) { "invalid_job_id" }
        check(Looper.myLooper() != Looper.getMainLooper()) { "execution_on_main_thread" }
        val job = Job()
        check(active.putIfAbsent(id, job) == null) { "job_already_running" }
        try {
            val deadline = SystemClock.elapsedRealtime() + JSONObject(code).optInt("timeout", 120).coerceIn(1, 3600) * 1000L
            while (!serial.tryLock(100, TimeUnit.MILLISECONDS)) {
                if (job.cancelled) return failure("cancelled", cancelled = true).put("side_effects_possible", false).toString()
                if (SystemClock.elapsedRealtime() >= deadline) return failure("execution_busy").put("side_effects_possible", false).toString()
            }
            try {
                if (job.cancelled) return failure("cancelled", cancelled = true).put("side_effects_possible", false).toString()
                return executeBound(id, code, job)
            } finally { serial.unlock() }
        } finally { active.remove(id, job) }
    }

    private fun executeBound(id: String, code: String, job: Job): String {
        pruneCompleted()
        val root = File(context.filesDir, "userdata/remote_runs/$id").apply { mkdirs() }
        val workspace = File(context.filesDir, "userdata/remote_work").apply { mkdirs() }
        val command = JSONObject(code)
        val seconds = command.optInt("timeout", 120).coerceIn(1, 3600)
        val request = File(root, "request.json")
        request.writeText(JSONObject().put("command", command).put("base_path", BaseBundle.ensure(context))
            .put("workspace", workspace.absolutePath).toString())
        val receiver = Messenger(Handler(Looper.getMainLooper()) { message ->
            when (message.what) {
                10 -> { job.pid = message.arg1; job.birth = WorkerProcessTree.info(job.pid)?.second }
                2 -> { job.result = message.data.getString("result"); job.done.countDown() }
                3 -> { job.error = message.data.getString("error"); job.done.countDown() }
                20 -> {
                    val method = message.data.getString("method") ?: ""
                    val args = message.data.getString("args") ?: "[]"
                    val callId = message.arg1
                    val replyTo = message.replyTo
                    val thread = Thread {
                        try {
                        val reply = if (job.cancelled || job.done.count == 0L) failure("job_not_active").toString()
                        else RemoteDeviceCalls.call(method, args)
                        try {
                            val file = File(root, "call-$callId.json")
                            file.writeText(reply)
                            replyTo.send(Message.obtain(null, 21, callId, 0).apply {
                                data = Bundle().apply { putString("result_path", file.absolutePath) }
                            })
                        } catch (_: Throwable) { /* Worker may already be gone. */ }
                        } finally { job.calls.remove(Thread.currentThread()) }
                    }
                    job.calls.add(thread)
                    thread.start()
                }
            }
            true
        })
        val bound = CountDownLatch(1)
        var didBind = false
        val connection = object : ServiceConnection {
            override fun onServiceConnected(name: ComponentName, binder: IBinder) {
                try {
                    if (!job.cancelled) Messenger(binder).send(Message.obtain(null, 1).apply {
                        replyTo = receiver
                        data = Bundle().apply { putString("request", request.absolutePath) }
                    }) else job.done.countDown()
                } catch (error: Throwable) { job.error = error.toString(); job.done.countDown() }
            }
            override fun onServiceDisconnected(name: ComponentName) {
                if (job.result == null) job.error = "worker_died"
                job.done.countDown()
            }
            override fun onNullBinding(name: ComponentName) { job.error = "worker_bind_failed"; job.done.countDown() }
        }
        val start = SystemClock.elapsedRealtime()
        main.post {
            try {
                didBind = context.bindService(Intent(context, RemoteExecutionService::class.java), connection, Context.BIND_AUTO_CREATE)
                if (!didBind) { job.error = "worker_bind_failed"; job.done.countDown() }
            } catch (error: Throwable) { job.error = error.toString(); job.done.countDown() }
            finally { bound.countDown() }
        }
        var completed = false
        var cleanupConfirmed = false
        var resourceCleanup = false
        try {
            completed = job.done.await(seconds.toLong(), TimeUnit.SECONDS)
        } finally {
            job.cancelled = job.cancelled || !completed
            // Wait for main-thread binding before releasing; never leak a late service bind.
            bound.await()
            job.calls.forEach { it.interrupt() }
            cleanupConfirmed = WorkerProcessTree.terminate(job.pid, job.birth)
            val released = CountDownLatch(1)
            main.post {
                try { if (didBind) context.unbindService(connection) }
                finally { released.countDown() }
            }
            released.await()
            val callDeadline = SystemClock.elapsedRealtime() + 3000
            for (thread in job.calls.toList()) {
                thread.join((callDeadline - SystemClock.elapsedRealtime()).coerceAtLeast(1))
            }
            resourceCleanup = job.calls.isEmpty()
        }
        val result = when {
            !completed -> failure("execution_timeout").put("timeout", true)
            job.cancelled -> failure("cancelled", cancelled = true)
            job.result != null && File(job.result!!).canonicalPath == File(root, "result.json").canonicalPath ->
                try { JSONObject(File(job.result!!).readText()) } catch (_: Throwable) { failure("worker_result_invalid") }
            else -> failure(job.error ?: "worker_result_missing").put("unknown", true)
        }
        result.put("worker_cleanup_confirmed", cleanupConfirmed).put("resource_cleanup_confirmed", resourceCleanup)
            .put("descendant_cleanup_scope", "observed_process_tree")
        if (!cleanupConfirmed || !resourceCleanup) {
            result.put("execution_error", result.opt("error"))
                .put("cancel_requested", job.cancelled).put("cancelled", false)
                .put("success", false).put("unknown", true).put("error", "cleanup_unconfirmed")
        }
        result.put("elapsed_ms", SystemClock.elapsedRealtime() - start).put("uid", Process.myUid()).put("identity", "app")
        run {
            val artifacts = JSONArray()
            for (stream in listOf("stdout", "stderr")) {
                val file = File(root, "$stream.log")
                if (file.exists()) {
                    val preview = file.inputStream().use { it.readBytesLimited(65536) }.toString(Charsets.UTF_8)
                    result.put(stream, preview)
                    val digest = java.security.MessageDigest.getInstance("SHA-256")
                    file.inputStream().use { input ->
                        val bytes = ByteArray(8192)
                        while (true) { val n = input.read(bytes); if (n < 0) break; digest.update(bytes, 0, n) }
                    }
                    artifacts.put(JSONObject().put("path", file.absolutePath).put("size", file.length())
                        .put("sha256", digest.digest().joinToString("") { "%02x".format(it) }))
                } else result.put(stream, "")
            }
            result.put("artifacts", artifacts)
        }
        File(root, "completed.json").writeText(result.toString())
        return result.toString()
    }

    private fun pruneCompleted() {
        val runs = File(context.filesDir, "userdata/remote_runs").apply { mkdirs() }
        java.io.RandomAccessFile(File(runs, ".retention.lock"), "rw").use { file ->
            file.channel.lock().use {
                val cutoff = System.currentTimeMillis() - TimeUnit.DAYS.toMillis(7)
                runs.listFiles()?.filter { it.isDirectory }?.forEach { dir ->
                    val completed = File(dir, "completed.json")
                    if (completed.exists() && completed.lastModified() < cutoff &&
                        dir.listFiles()?.none { it.name.startsWith(".transfer-") } == true) dir.deleteRecursively()
                }
            }
        }
    }

    private fun java.io.InputStream.readBytesLimited(limit: Int): ByteArray {
        val bytes = ByteArray(limit)
        var size = 0
        while (size < limit) { val n = read(bytes, size, limit - size); if (n < 0) break; size += n }
        return bytes.copyOf(size)
    }

    private fun failure(code: String, cancelled: Boolean = false) = JSONObject()
        .put("success", false).put("error", code).put("exit_code", JSONObject.NULL)
        .put("cancelled", cancelled).put("side_effects_possible", true)

}
