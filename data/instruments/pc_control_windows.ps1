# Shared Windows PC controls. Windows PowerShell 5.1 + built-in Core Audio COM.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$result = @{ protocol='pc-control/1'; platform='windows'; action=$PcRequest.action; request_id=$PcRequest.request_id; success=$false; verified=$false }
try {
    if ($env:OS -ne 'Windows_NT') { throw 'Windows 전용 실행 파일입니다.' }
    $result.hostname = $env:COMPUTERNAME
    $result.os_version = [Environment]::OSVersion.Version.ToString()
    $result.observed_at = [DateTime]::UtcNow.ToString('o')
    $result.can_lock = $true
    if ($PcRequest.action -in @('status','volume','mute')) {
        Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
namespace IndieBizPC {
 [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class Enumerator {}
 [ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
 interface IEnum {
  [PreserveSig] int EnumAudioEndpoints(int flow, uint mask, out ICollection devices);
  [PreserveSig] int GetDefaultAudioEndpoint(int flow, int role, out IDevice device);
  [PreserveSig] int GetDevice([MarshalAs(UnmanagedType.LPWStr)] string id, out IDevice device);
 }
 [ComImport, Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
 interface ICollection {
  [PreserveSig] int GetCount(out uint count);
  [PreserveSig] int Item(uint index, out IDevice device);
 }
 [ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
 interface IDevice {
  [PreserveSig] int Activate(ref Guid iid, uint context, IntPtr parameters, [MarshalAs(UnmanagedType.IUnknown)] out object value);
  [PreserveSig] int OpenPropertyStore(uint access, out IProperties properties);
  [PreserveSig] int GetId([MarshalAs(UnmanagedType.LPWStr)] out string id);
  [PreserveSig] int GetState(out uint state);
 }
 [StructLayout(LayoutKind.Sequential)] struct Key { public Guid guid; public uint id; }
 [StructLayout(LayoutKind.Explicit, Size=24)] struct Variant {
  [FieldOffset(0)] public ushort type;
  [FieldOffset(8)] public IntPtr pointer;
 }
 [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
 interface IProperties {
  [PreserveSig] int GetCount(out uint count);
  [PreserveSig] int GetAt(uint index, out Key key);
  [PreserveSig] int GetValue(ref Key key, out Variant value);
 }
 [ComImport, Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
 interface IVolume {
  [PreserveSig] int RegisterControlChangeNotify(IntPtr notify);
  [PreserveSig] int UnregisterControlChangeNotify(IntPtr notify);
  [PreserveSig] int GetChannelCount(out uint channels);
  [PreserveSig] int SetMasterVolumeLevel(float db, ref Guid context);
  [PreserveSig] int SetMasterVolumeLevelScalar(float level, ref Guid context);
  [PreserveSig] int GetMasterVolumeLevel(out float db);
  [PreserveSig] int GetMasterVolumeLevelScalar(out float level);
  [PreserveSig] int SetChannelVolumeLevel(uint channel, float db, ref Guid context);
  [PreserveSig] int SetChannelVolumeLevelScalar(uint channel, float level, ref Guid context);
  [PreserveSig] int GetChannelVolumeLevel(uint channel, out float db);
  [PreserveSig] int GetChannelVolumeLevelScalar(uint channel, out float level);
  [PreserveSig] int SetMute([MarshalAs(UnmanagedType.Bool)] bool mute, ref Guid context);
  [PreserveSig] int GetMute([MarshalAs(UnmanagedType.Bool)] out bool mute);
 }
 public class Output {
  public string id, name, capability_basis;
  public int volume;
  public bool muted, is_default, can_set_volume, can_mute;
 }
 public static class Audio {
  [DllImport("ole32.dll")] static extern int PropVariantClear(ref Variant value);
  static void Check(int status) { Marshal.ThrowExceptionForHR(status); }
  static void Release(object value) { if(value != null && Marshal.IsComObject(value)) Marshal.ReleaseComObject(value); }
  static string Id(IDevice device) { string id; Check(device.GetId(out id)); return id; }
  static IVolume Volume(IDevice device) {
   Guid iid=typeof(IVolume).GUID; object value; Check(device.Activate(ref iid,23,IntPtr.Zero,out value)); return (IVolume)value;
  }
  static string Name(IDevice device) {
   IProperties store=null;
   try {
    Check(device.OpenPropertyStore(0,out store));
    Key key=new Key { guid=new Guid("a45c254e-df1c-4efd-8020-67d146a850e0"), id=14 };
    Variant value; Check(store.GetValue(ref key,out value));
    try { return value.type==31 ? Marshal.PtrToStringUni(value.pointer) : Id(device); }
    finally { PropVariantClear(ref value); }
   } finally { Release(store); }
  }
  static Output Read(IDevice device, string defaultId) {
   IVolume audio=null;
   try {
    uint state; Check(device.GetState(out state)); if(state!=1) throw new InvalidOperationException("출력 장치가 연결되지 않았습니다.");
    audio=Volume(device); float level; bool mute; Check(audio.GetMasterVolumeLevelScalar(out level)); Check(audio.GetMute(out mute));
    string id=Id(device);
    // EndpointVolume provides OS controls, including software fallback. No setter is called by status.
    return new Output {id=id, name=Name(device), volume=(int)Math.Round(level*100), muted=mute, is_default=id==defaultId,
                       can_set_volume=true, can_mute=true, capability_basis="wasapi_endpoint_volume_interface"};
   } finally { Release(audio); }
  }
  public static Output[] List() {
   IEnum enumerator=null; ICollection collection=null; IDevice defaultDevice=null;
   try {
    enumerator=(IEnum)new Enumerator(); string defaultId=null;
    if(enumerator.GetDefaultAudioEndpoint(0,1,out defaultDevice)>=0) defaultId=Id(defaultDevice);
    Check(enumerator.EnumAudioEndpoints(0,1,out collection)); uint count; Check(collection.GetCount(out count));
    var rows=new List<Output>();
    for(uint i=0;i<count;i++) { IDevice device=null; try { Check(collection.Item(i,out device)); rows.Add(Read(device,defaultId)); } finally { Release(device); } }
    return rows.ToArray();
   } finally { Release(defaultDevice); Release(collection); Release(enumerator); }
  }
  public static Output Change(string id, string action, int level, bool muted) {
   IEnum enumerator=null; IDevice device=null; IVolume audio=null;
   try {
    if(String.IsNullOrWhiteSpace(id)) throw new ArgumentException("출력 장치를 지정하세요.");
    if(action!="volume" && action!="mute") throw new ArgumentException("알 수 없는 동작입니다.");
    if(level<0 || level>100) throw new ArgumentException("음량 범위는 0~100입니다.");
    enumerator=(IEnum)new Enumerator(); Check(enumerator.GetDevice(id,out device));
    Read(device,null); audio=Volume(device); Guid context=Guid.Empty;
    if(action=="volume") Check(audio.SetMasterVolumeLevelScalar(level/100f,ref context));
    else Check(audio.SetMute(muted,ref context));
    Output after=Read(device,null);
    if(action=="volume" ? Math.Abs(after.volume-level)>1 : after.muted!=muted) throw new InvalidOperationException("설정값을 확인하지 못했습니다.");
    return after;
   } finally { Release(audio); Release(device); Release(enumerator); }
  }
 }
}
'@
        if ($PcRequest.action -eq 'status') {
            try { $result.devices = @([IndieBizPC.Audio]::List()) }
            catch { $result.devices = @(); $result.audio_error = $_.Exception.Message }
            $result.message = 'Windows PC 상태를 조회했습니다.'
        } else {
            $result.device = [IndieBizPC.Audio]::Change([string]$PcRequest.device_id, [string]$PcRequest.action, [int]$PcRequest.value, [bool]$PcRequest.enabled)
            $result.devices = @([IndieBizPC.Audio]::List())
            $result.message = '출력 장치의 실제 설정값을 확인했습니다.'
        }
        $result.verified = $true
    } elseif ($PcRequest.action -eq 'open_url') {
        $uri = [Uri]$PcRequest.url
        if ($uri.Scheme -notin @('http','https') -or $uri.UserInfo) { throw '허용하지 않는 웹 주소입니다.' }
        Start-Process -FilePath $uri.AbsoluteUri
        $result.message = '기본 브라우저에 주소 열기를 요청했습니다. 로딩·재생은 확인하지 않았습니다.'
    } elseif ($PcRequest.action -eq 'lock') {
        Add-Type -TypeDefinition 'using System.Runtime.InteropServices; public static class PCLock { [DllImport("user32.dll", SetLastError=true)] [return: MarshalAs(UnmanagedType.Bool)] public static extern bool LockWorkStation(); }'
        if (-not [PCLock]::LockWorkStation()) { throw '화면 잠금 요청이 거절됐습니다.' }
        $result.message = '화면 잠금을 요청했습니다. 잠금 상태는 확인하지 않았습니다.'
    } else { throw '지원하지 않는 동작입니다.' }
    $result.success = $true
} catch {
    $result.error = $_.Exception.Message
}
Write-Output ('INDIEBIZ_PC_RESULT:' + (ConvertTo-Json -InputObject $result -Depth 7 -Compress))
