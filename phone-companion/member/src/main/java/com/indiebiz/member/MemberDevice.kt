package com.indiebiz.member

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** 위치는 허브 캐시가 아니라 이 기기에서 한 번 측정한다. 상시 추적하지 않는다. */
object MemberDevice {
    @Suppress("DEPRECATION")
    fun location(context:Context):JSONObject {
        if(context.checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION)!=PackageManager.PERMISSION_GRANTED &&
            context.checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)!=PackageManager.PERMISSION_GRANTED)
            return MemberStore.error("회원 화면의 위치 허용 버튼에서 권한을 켜주세요")
        val manager=context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
        val latch=CountDownLatch(1)
        var measured:Location?=null
        val listener=object:LocationListener {
            override fun onLocationChanged(location:Location) { measured=location; latch.countDown() }
            override fun onProviderEnabled(provider:String) {}
            override fun onProviderDisabled(provider:String) {}
            override fun onStatusChanged(provider:String?,status:Int,extras:Bundle?) {}
        }
        try {
            val fine=context.checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)==PackageManager.PERMISSION_GRANTED
            val providers=manager.getProviders(true).filter { it==LocationManager.NETWORK_PROVIDER || (fine && it==LocationManager.GPS_PROVIDER) }
            if(providers.isEmpty())return MemberStore.error("기기의 위치 서비스를 켜주세요")
            for(provider in providers)manager.requestSingleUpdate(provider,listener,Looper.getMainLooper())
            if(!latch.await(30,TimeUnit.SECONDS))return MemberStore.error("위치 측정 시간 초과")
            val result=measured ?: return MemberStore.error("위치 측정 실패")
            return JSONObject().put("success",true).put("latitude",result.latitude).put("longitude",result.longitude)
                .put("accuracy_m",result.accuracy).put("source",result.provider).put("measured_at",result.time)
        } finally { manager.removeUpdates(listener) }
    }
}
