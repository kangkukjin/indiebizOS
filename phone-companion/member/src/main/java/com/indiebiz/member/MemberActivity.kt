package com.indiebiz.member
import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.os.Build
import android.provider.Settings
import android.text.InputType
import android.webkit.*
import android.widget.*
import org.json.JSONObject
import java.util.concurrent.atomic.AtomicInteger

class MemberActivity:Activity() {
    private lateinit var runtime:MemberRuntime
    private var web:WebView?=null
    private var pendingExport:java.io.File?=null
    private val generation=AtomicInteger()
    override fun onCreate(state:Bundle?) {
        super.onCreate(state); runtime=MemberRuntime.get(this)
        if(Build.VERSION.SDK_INT>=33) requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS),1)
        if(runtime.base().isEmpty() || runtime.key().isEmpty()) setup() else showChat()
    }
    private fun setup() {
        val box=LinearLayout(this).apply { orientation=LinearLayout.VERTICAL; setPadding(32,60,32,24) }
        box.addView(TextView(this).apply { text="IndieBiz 회원\n허브 주소와 발급받은 회원 키를 입력하세요."; textSize=22f })
        val base=EditText(this).apply { hint="https://허브주소"; setText(runtime.base()); inputType=InputType.TYPE_TEXT_VARIATION_URI }
        val key=EditText(this).apply { hint="회원 키"; inputType=InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD }
        box.addView(base);box.addView(key)
        box.addView(Button(this).apply { text="연결"; setOnClickListener {
            val url=base.text.toString().trim().trimEnd('/')
            if(!url.startsWith("https://") || key.text.isEmpty()) { Toast.makeText(this@MemberActivity,"HTTPS 주소와 키를 확인하세요",Toast.LENGTH_LONG).show(); return@setOnClickListener }
            runtime.prefs.edit().putString("base",url).commit(); MemberKeyStore.write(this@MemberActivity,key.text.toString()); showChat()
        } })
        setContentView(box)
    }
    private fun showChat() {
        startForegroundService(Intent(this,AgentForegroundService::class.java))
        val layout=LinearLayout(this).apply { orientation=LinearLayout.VERTICAL }
        val bar=LinearLayout(this)
        bar.addView(Button(this).apply { text="파일 가져오기"; setOnClickListener { startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).setType("*/*").addCategory(Intent.CATEGORY_OPENABLE),2) } })
        bar.addView(Button(this).apply { text="파일 내보내기"; setOnClickListener { exportFile() } })
        bar.addView(Button(this).apply { text="접근성 설정"; setOnClickListener { startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) } })
        bar.addView(Button(this).apply { text="위치 허용"; setOnClickListener {
            requestPermissions(arrayOf(android.Manifest.permission.ACCESS_FINE_LOCATION,android.Manifest.permission.ACCESS_COARSE_LOCATION),4)
        } })
        val scroller=HorizontalScrollView(this).apply { addView(bar) }
        layout.addView(scroller)
        val v=WebView(this);web=v
        v.settings.javaScriptEnabled=true
        v.settings.allowFileAccess=false;v.settings.allowContentAccess=false
        v.settings.mixedContentMode=WebSettings.MIXED_CONTENT_NEVER_ALLOW
        v.webViewClient=object:WebViewClient() {
            override fun shouldOverrideUrlLoading(view:WebView?,request:WebResourceRequest?):Boolean=true
        }
        val gen=generation.incrementAndGet()
        val bridgeToken=java.util.UUID.randomUUID().toString()
        v.addJavascriptInterface(object {
            @JavascriptInterface fun request(id:String,path:String,raw:String,token:String) {
                if(token!=bridgeToken)return
                if(id.length>64 || raw.length>1024*1024)return
                runtime.workers.execute {
                    val out=try { runtime.local(path,JSONObject(raw)) } catch(e:Exception) { MemberStore.error("연결/요청 실패") }
                    runOnUiThread { if(generation.get()==gen) {
                        v.evaluateJavascript("window.memberNativeResult("+JSONObject.quote(id)+","+out.toString()+")",null)
                        if(path=="export" && out is JSONObject && out.optBoolean("success")) {
                            pendingExport=java.io.File(out.getString("path"))
                            startActivityForResult(Intent(Intent.ACTION_CREATE_DOCUMENT).setType("application/zip")
                                .addCategory(Intent.CATEGORY_OPENABLE).putExtra(Intent.EXTRA_TITLE,pendingExport!!.name),3)
                        }
                    } }
                }
            }
        },"MemberBridge")
        layout.addView(v,LinearLayout.LayoutParams(-1,0,1f));setContentView(layout)
        runtime.workers.execute {
            try { val html=runtime.html().replaceFirst("<script>window.__MEMBER", "<script>window.__NATIVE_TOKEN="+JSONObject.quote(bridgeToken)+";window.__MEMBER");runOnUiThread { if(generation.get()==gen)v.loadDataWithBaseURL("https://member.local/",html,"text/html","UTF-8",null) } }
            catch(e:Exception) { runOnUiThread { Toast.makeText(this,"화면을 불러올 수 없습니다. 연결을 확인하세요.",Toast.LENGTH_LONG).show() } }
        }
    }
    private fun exportFile() {
        val files=runtime.store.path("").walkTopDown().filter { it.isFile }.take(200).toList()
        if(files.isEmpty()) { Toast.makeText(this,"저장된 파일이 없습니다",Toast.LENGTH_LONG).show(); return }
        android.app.AlertDialog.Builder(this).setTitle("내보낼 파일 선택")
            .setItems(files.map { it.relativeTo(runtime.store.path("")).path }.toTypedArray()) { _,index ->
                pendingExport=runtime.store.path(files[index].path)
                val mime=MimeTypeMap.getSingleton().getMimeTypeFromExtension(files[index].extension.lowercase()) ?: "application/octet-stream"
                startActivityForResult(Intent(Intent.ACTION_CREATE_DOCUMENT).setType(mime).addCategory(Intent.CATEGORY_OPENABLE)
                    .putExtra(Intent.EXTRA_TITLE,files[index].name),3)
            }.setNegativeButton("취소",null).show()
    }
    @Deprecated("Legacy Android result supported by minSdk")
    override fun onActivityResult(request:Int,result:Int,data:Intent?) {
        super.onActivityResult(request,result,data)
        if(request==3 && result==RESULT_OK) data?.data?.let { uri ->
            val file=pendingExport ?: return@let
            runtime.workers.execute {
                try { contentResolver.openOutputStream(uri)!!.use { out -> file.inputStream().use { it.copyTo(out) } } }
                catch(e:Exception) { runOnUiThread { Toast.makeText(this,"내보내기 저장 실패",Toast.LENGTH_LONG).show() } }
            }
        }
        if(request==2 && result==RESULT_OK) data?.data?.let { uri ->
            runtime.workers.execute {
                try {
                    var display="file"
                    contentResolver.query(uri,arrayOf(android.provider.OpenableColumns.DISPLAY_NAME),null,null,null)?.use { cursor ->
                        if(cursor.moveToFirst())display=cursor.getString(0) ?: "file"
                    }
                    val safe=display.replace(Regex("[^가-힣A-Za-z0-9._ -]"),"_").takeLast(160)
                    val name="가져온파일-"+System.currentTimeMillis()+"-"+safe
                    val target=runtime.store.path(name)
                    try { contentResolver.openInputStream(uri)!!.use { input -> target.outputStream().use { output ->
                        val buffer=ByteArray(8192); var total=0
                        while(true) { val count=input.read(buffer); if(count<0)break; total+=count
                            require(total<=32*1024*1024) { "파일은 32MB까지 가져올 수 있습니다" }; output.write(buffer,0,count) }
                    } } } catch(e:Exception) { target.delete(); throw e }
                    runOnUiThread { Toast.makeText(this,"저장됨: "+name,Toast.LENGTH_LONG).show() }
                } catch(e:Exception) { runOnUiThread { Toast.makeText(this,"파일 가져오기 실패",Toast.LENGTH_LONG).show() } }
            }
        }
    }
    override fun onDestroy() { generation.incrementAndGet();web?.removeJavascriptInterface("MemberBridge");web?.destroy();super.onDestroy() }
}
