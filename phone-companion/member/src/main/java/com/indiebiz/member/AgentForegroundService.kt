package com.indiebiz.member
import android.app.*
import android.content.Intent
import android.os.IBinder

class AgentForegroundService:Service() {
    override fun onBind(intent:Intent?):IBinder?=null
    override fun onStartCommand(intent:Intent?,flags:Int,startId:Int):Int {
        if(intent?.action=="stop") { MemberRuntime.get(this).active=false; stopSelf(); return START_NOT_STICKY }
        val nm=getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel("member","회원 연결",NotificationManager.IMPORTANCE_LOW))
        val open=PendingIntent.getActivity(this,0,Intent(this,MemberActivity::class.java),PendingIntent.FLAG_IMMUTABLE)
        val stop=PendingIntent.getService(this,1,Intent(this,AgentForegroundService::class.java).setAction("stop"),PendingIntent.FLAG_IMMUTABLE)
        startForeground(31,Notification.Builder(this,"member").setContentTitle("IndieBiz 회원 연결")
            .setContentText("대화와 실행 결과는 이 기기에 저장됩니다").setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentIntent(open).addAction(Notification.Action.Builder(null,"연결 중단",stop).build()).build())
        MemberRuntime.get(this).connectLoop()
        return START_NOT_STICKY
    }
    override fun onDestroy() { MemberRuntime.get(this).active=false; super.onDestroy() }
}
