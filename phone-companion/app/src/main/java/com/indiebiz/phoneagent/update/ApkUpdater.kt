package com.indiebiz.phoneagent.update

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.admin.DevicePolicyManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInfo
import android.content.pm.PackageInstaller
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import java.util.zip.ZipFile

/** Only registered hardware receives this command. Android owns package replacement.
 * State lives outside the replaceable Python bundle and is reported at every hub sync.
 */
object ApkUpdater {
    private lateinit var ctx: Context
    private var installedHash: String? = null
    private const val CHANNEL = "central_apk_update"
    private const val NOTICE = 1005
    private val active = setOf("staged", "installing", "awaiting_permission", "awaiting_confirmation")
    private val prefs get() = ctx.getSharedPreferences("central_apk_update", Context.MODE_PRIVATE)
    private fun read() = JSONObject(prefs.getString("attempt", "{}") ?: "{}")
    private fun save(value: JSONObject) {
        check(prefs.edit().putString("attempt", value.toString()).commit()) { "update_state_write_failed" }
    }
    private fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
    private fun hash(file: File): String {
        val md = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buf = ByteArray(1024 * 1024)
            while (true) { val n = input.read(buf); if (n < 0) break; md.update(buf, 0, n) }
        }
        return md.digest().joinToString("") { "%02x".format(it) }
    }
    // Samsung Android 9 only collects archive certificates when GET_SIGNATURES is also
    // requested. Still verify signingInfo (the actual current signer), never a legacy fallback.
    @Suppress("DEPRECATION") private fun signatureFlags() = PackageManager.GET_SIGNING_CERTIFICATES or
        if (Build.VERSION.SDK_INT == 28) PackageManager.GET_SIGNATURES else 0
    @Suppress("DEPRECATION") private fun current() = ctx.packageManager.getPackageInfo(ctx.packageName, signatureFlags())
    private fun signer(info: PackageInfo): String {
        val signatures = info.signingInfo?.apkContentsSigners ?: error("apk_signer_missing")
        require(signatures.size == 1) { "multiple_apk_signers_unsupported" }
        return sha(signatures[0].toByteArray())
    }
    private fun abi() = if (android.os.Process.is64Bit()) "arm64-v8a" else "armeabi-v7a"
    private fun isDeviceOwner() = ctx.getSystemService(DevicePolicyManager::class.java).isDeviceOwnerApp(ctx.packageName)
    internal fun canInstall() = isDeviceOwner() || ctx.packageManager.canRequestPackageInstalls()

    @JvmStatic @Synchronized fun init(context: Context) {
        if (::ctx.isInitialized) return
        ctx = context.applicationContext
        Thread { resumeInstall() }.start()
    }

    @JvmStatic @Synchronized fun capabilities(): String {
        val info = current()
        val digest = installedHash ?: hash(File(ctx.applicationInfo.sourceDir)).also { installedHash = it }
        val attempt = read()
        if (attempt.optString("sha256") == digest && attempt.optString("state") != "installed") {
            attempt.put("state", "installed").put("message", "새 APK로 재접속")
            save(attempt)
            File(attempt.optString("path")).takeIf { it.parentFile == File(ctx.filesDir, "userdata/apk-updates") }?.delete()
            ctx.getSystemService(NotificationManager::class.java).cancel(NOTICE)
        } else if (attempt.optString("state") in active &&
            System.currentTimeMillis() - attempt.optLong("started_ms") > 60 * 60 * 1000) {
            try { ctx.packageManager.packageInstaller.abandonSession(attempt.optInt("session_id", -1)) } catch (_: Exception) { }
            attempt.put("state", "failed").put("message", "설치 완료를 1시간 안에 확인하지 못했습니다. 중앙에서 다시 시도하세요.")
            save(attempt)
        }
        return JSONObject().put("contract", 1).put("abi", abi()).put("sdk", Build.VERSION.SDK_INT)
            .put("version_code", info.longVersionCode).put("version_name", info.versionName)
            .put("installed_sha256", digest).put("signer_sha256", signer(info))
            .put("can_install", canInstall()).put("device_owner", isDeviceOwner()).put("attempt", attempt).toString()
    }

    @Suppress("DEPRECATION") private fun validate(path: String, release: JSONObject): File {
        val file = File(path).canonicalFile
        require(file.parentFile == File(ctx.filesDir, "userdata/apk-updates").canonicalFile) { "invalid_apk_path" }
        require(file.length() == release.getLong("size") && hash(file) == release.getString("sha256")) { "apk_hash_mismatch" }
        val archive = ctx.packageManager.getPackageArchiveInfo(file.path, signatureFlags())
            ?: error("invalid_apk")
        val installed = current()
        require(archive.packageName == ctx.packageName && release.getString("package") == ctx.packageName) { "apk_package_mismatch" }
        require(archive.longVersionCode == release.getLong("version_code") && archive.longVersionCode > installed.longVersionCode) { "apk_version_not_newer" }
        require(signer(archive) == signer(installed) && signer(archive) == release.getString("signer_sha256")) { "apk_signer_mismatch" }
        require(release.getString("abi") == abi() && release.getInt("min_sdk") <= Build.VERSION.SDK_INT) { "apk_device_mismatch" }
        ZipFile(file).use { zip ->
            val nativeAbis = zip.entries().asSequence().map { it.name }.filter { it.startsWith("lib/") && it.endsWith(".so") }
                .map { it.split('/')[1] }.toSet()
            require(nativeAbis == setOf(abi())) { "apk_abi_mismatch" }
        }
        return file
    }

    @JvmStatic @Synchronized fun install(path: String, manifest: String, jobId: String): String {
        val previous = read()
        if (previous.optString("state") in active) return JSONObject().put("success", false).put("error", "phone_update_busy").toString()
        val release = JSONObject(manifest)
        validate(path, release)
        require(File(ctx.filesDir, "secrets/limb_client.json").isFile) { "phone_not_registered" }
        save(JSONObject().put("job_id", jobId).put("sha256", release.getString("sha256"))
            .put("path", path).put("release", release).put("started_ms", System.currentTimeMillis()).put("state", "staged"))
        // The OS installer and manifest receivers own the steps after this process dies.
        Thread { resumeInstall() }.start()
        return JSONObject().put("success", true).put("accepted", true).put("state", "staged").toString()
    }

    @JvmStatic @Synchronized fun resumeInstall() {
        val value = read()
        if (value.optString("state") !in setOf("staged", "awaiting_permission")) return
        try {
            if (!canInstall()) {
                value.put("state", "awaiting_permission").put("message", "폰에서 IndieBiz의 앱 설치 허용이 필요합니다")
                save(value)
                prompt(Intent(ctx, UpdatePermissionActivity::class.java), value.getString("message"))
                return
            }
            val file = validate(value.getString("path"), value.getJSONObject("release"))
            val installer = ctx.packageManager.packageInstaller
            val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL).apply {
                setAppPackageName(ctx.packageName)
                setSize(file.length())
                if (Build.VERSION.SDK_INT >= 31) setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED)
            }
            val id = installer.createSession(params)
            value.put("session_id", id).put("state", "installing").put("message", "Android 설치 처리 중")
            save(value)
            try {
                installer.openSession(id).use { session ->
                    session.openWrite("base.apk", 0, file.length()).use { output ->
                        file.inputStream().use { it.copyTo(output) }; session.fsync(output)
                    }
                    val callback = Intent(ctx, UpdateResultReceiver::class.java).setAction("${ctx.packageName}.APK_UPDATE_RESULT")
                    val flags = PendingIntent.FLAG_UPDATE_CURRENT or if (Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_MUTABLE else 0
                    session.commit(PendingIntent.getBroadcast(ctx, id, callback, flags).intentSender)
                }
            } catch (error: Exception) {
                try { installer.abandonSession(id) } catch (_: Exception) { }
                throw error
            }
        } catch (error: Exception) {
            value.put("state", "failed").put("message", error.message ?: "APK 설치 실패")
            save(value)
        }
    }

    @Synchronized fun onResult(intent: Intent) {
        val value = read()
        if (intent.getIntExtra(PackageInstaller.EXTRA_SESSION_ID, -2) != value.optInt("session_id", -1)) return
        when (intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)) {
            PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                @Suppress("DEPRECATION") val confirmation = intent.getParcelableExtra<Intent>(Intent.EXTRA_INTENT)
                value.put("state", "awaiting_confirmation").put("message", "Android가 폰에서 설치 확인을 요구합니다")
                save(value)
                if (confirmation != null) prompt(confirmation, value.getString("message"))
            }
            PackageInstaller.STATUS_SUCCESS -> {
                // Success is not a hub health check. capabilities() confirms the bytes after restart.
                value.put("state", "installing").put("message", "APK 설치됨 · 새 앱 재접속 확인 중")
                save(value)
                com.indiebiz.phoneagent.AgentForegroundService.start(ctx)
            }
            else -> {
                value.put("state", "failed").put("message", intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE) ?: "Android 설치 실패")
                save(value)
            }
        }
    }

    private fun prompt(intent: Intent, message: String) {
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        val nm = ctx.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CHANNEL, "중앙 앱 업데이트", NotificationManager.IMPORTANCE_HIGH))
        val action = PendingIntent.getActivity(ctx, NOTICE, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        try {
            nm.notify(NOTICE, Notification.Builder(ctx, CHANNEL).setSmallIcon(android.R.drawable.stat_sys_download_done)
                .setContentTitle("중앙에서 앱 업데이트 요청").setContentText(message).setContentIntent(action).setAutoCancel(true).build())
        } catch (_: SecurityException) { }
        // Existing overlay permission may permit foregrounding; otherwise the notification remains.
        Handler(Looper.getMainLooper()).post { try { ctx.startActivity(intent) } catch (_: Exception) { } }
    }

    fun needsPermission() = read().optString("state") == "awaiting_permission"
}
