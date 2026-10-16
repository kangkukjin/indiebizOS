package com.indiebiz.ui

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.security.KeyPairGenerator
import java.security.MessageDigest
import java.security.Signature
import java.util.Base64

class SurfaceReleaseVerifierTest {
    private val key=KeyPairGenerator.getInstance("Ed25519").generateKeyPair()
    private val display=JSONObject().put("format","indiebiz-display-1").put("surface","member").put("state",1).put("host","a".repeat(64))
    private val bytes=display.toString().toByteArray()
    private val file=JSONObject().put("name","display.json").put("size",bytes.size).put("sha256",MessageDigest.getInstance("SHA-256").digest(bytes).joinToString(""){"%02x".format(it)}).put("url","https://example.test/ui/1/display.json")
    private fun manifest()=JSONObject().put("format","indiebiz-member-runtime").put("kind","ui").put("platform","android").put("arch","all").put("shell",3).put("protocol",2).put("state",1).put("sequence",1).put("version","1.0.0").put("host","a".repeat(64)).put("expires",System.currentTimeMillis()/1000+600).put("files",org.json.JSONArray().put(file))
    private fun envelope(m:JSONObject):JSONObject {
        val data=m.toString().toByteArray();val signature=Signature.getInstance("Ed25519");signature.initSign(key.private);signature.update(data)
        return JSONObject().put("manifest",Base64.getEncoder().encodeToString(data)).put("signature",Base64.getEncoder().encodeToString(signature.sign()))
    }
    private fun verifier(surface:String="member")=SurfaceReleaseVerifier(JSONObject().put("feed","https://example.test/current.json").put("publicKey","-----BEGIN PUBLIC KEY-----\n"+Base64.getEncoder().encodeToString(key.public.encoded)+"\n-----END PUBLIC KEY-----"),surface)
    private fun rejected(block:()->Unit){try{block();fail("must reject")}catch(error:Exception){assertNotNull(error)}}
    @Test fun signedPayloadAndOfflineBoot(){val v=verifier();val m=manifest();assertEquals("member",v.payload(v.verify(envelope(m)),bytes).getString("surface"));m.put("expires",1);rejected{v.verify(envelope(m))};v.verify(envelope(m),true)}
    @Test fun tamperedSignatureAndAsset(){val v=verifier();val e=envelope(manifest());e.put("manifest",Base64.getEncoder().encodeToString(manifest().put("sequence",2).toString().toByteArray()));rejected{v.verify(e)};rejected{v.payload(manifest(),bytes+1)}}
    @Test fun wrongHostSurfacePlatformAndOrigin(){val v=verifier();rejected{v.verify(envelope(manifest().put("platform","darwin")))};rejected{v.payload(manifest().put("host","b".repeat(64)),bytes)};rejected{verifier("phone").payload(manifest(),bytes)};file.put("url","https://foreign.test/a");rejected{v.verify(envelope(manifest()))}}
    @Test fun malformedAndUnknownContracts(){val v=verifier();for(field in listOf("shell","protocol","state"))rejected{v.verify(envelope(manifest().put(field,99)))};rejected{v.verify(envelope(manifest().put("sequence",0)))};rejected{v.verify(envelope(manifest().put("kind","runtime")))};rejected{v.origin("http://example.test/a")}}
}
