# Existing Chromium tabs through Windows UI Automation. No debug port, extension,
# clipboard, process termination, blind address shortcuts, or new browser windows.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$result = @{protocol='pc-control/1';platform='windows';action=$PcRequest.action;request_id=$PcRequest.request_id;success=$false;verified=$false}
$mutex = $null; $locked = $false
try {
    if ($env:OS -ne 'Windows_NT') { throw 'Windows 전용 실행 파일입니다.' }
    $mutex = New-Object System.Threading.Mutex($false, 'Local\IndieBizPCYouTube')
    $locked = $mutex.WaitOne(0)
    if (-not $locked) { throw '다른 유튜브 제어가 실행 중입니다. 완료 후 상태를 조회하세요.' }
    Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Windows.Forms, WindowsBase
    Add-Type -ReferencedAssemblies UIAutomationClient,UIAutomationTypes,System.Windows.Forms,WindowsBase -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows.Automation;
using System.Windows.Forms;

public static class PCYouTube {
 public static Observation Last;
 public class Tab {
  public AutomationElement window, element;
  public string identity, browser, url, video_id;
  public int hwnd;
 }
 public class Observation {
  public string url, video_id, title, browser, tab_id, state, player_error;
  public bool playing, paused, ad;
  public double position, previous_position, duration;
 }
 public class Inventory {
  public List<Tab> tabs = new List<Tab>();
  public int total_tabs;
 }
 [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr hwnd);
 [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] static extern bool SetCursorPos(int x,int y);
 const string PauseLabel = @"^(일시\s*중지|Pause)(\s*\(k\)|\s+키보드 단축키\s+k|\s+keyboard shortcut\s+k)$";
 const string PlayLabel = @"^(재생|Play)(\s*\(k\)|\s+키보드 단축키\s+k|\s+keyboard shortcut\s+k)$";
 static readonly TreeScope Desc = TreeScope.Descendants;
 static AutomationElementCollection All(AutomationElement e) { return e.FindAll(Desc, Condition.TrueCondition); }
 static string Id(AutomationElement e) { return String.Join(".", e.GetRuntimeId()); }
 static bool InPage(AutomationElement e) {
  for(var p=TreeWalker.ControlViewWalker.GetParent(e);p!=null;p=TreeWalker.ControlViewWalker.GetParent(p)) {
   if(p.Current.ControlType==ControlType.Document) return true;
   if(p.Current.ControlType==ControlType.Window) break;
  } return false;
 }
 static AutomationElement Find(AutomationElement root, Func<AutomationElement,bool> test) {
  foreach(AutomationElement e in All(root)) { try { if(test(e)) return e; } catch(ElementNotAvailableException) {} }
  return null;
 }
 static void Invoke(AutomationElement e) {
  if(e==null) throw new Exception("확인된 플레이어 버튼이 없습니다.");
  ((InvokePattern)e.GetCurrentPattern(InvokePattern.Pattern)).Invoke();
 }
 static AutomationElement Player(AutomationElement w) {
  return w.FindFirst(Desc,new PropertyCondition(AutomationElement.AutomationIdProperty,"movie_player"));
 }
 static AutomationElement Button(AutomationElement p, string pattern) {
  if(p==null) return null;
  foreach(AutomationElement e in p.FindAll(Desc,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Button))) {
   try { if(Regex.IsMatch(e.Current.Name,pattern,RegexOptions.IgnoreCase)) return e; } catch(ElementNotAvailableException) {}
  } return null;
 }
 static AutomationElement Address(AutomationElement w) {
  var found = new List<AutomationElement>();
  foreach(AutomationElement e in w.FindAll(Desc,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Edit))) {
   try { if(e.Current.AcceleratorKey.Replace(" ","").ToLowerInvariant()=="ctrl+l" && !InPage(e)) found.Add(e); } catch(ElementNotAvailableException) {}
  }
  if(found.Count!=1) throw new Exception("브라우저 주소창을 유일하게 식별하지 못했습니다. 검색창에 입력하지 않습니다.");
  return found[0];
 }
 static string URL(AutomationElement w) {
  string s=((ValuePattern)Address(w).GetCurrentPattern(ValuePattern.Pattern)).Current.Value;
  return s.Contains("://") ? s : "https://"+s;
 }
 static bool YouTube(string s) {
  Uri u; if(!Uri.TryCreate(s,UriKind.Absolute,out u)) return false;
  string h=u.Host.ToLowerInvariant().TrimEnd('.');
  return h=="youtube.com" || h.EndsWith(".youtube.com");
 }
 public static string VideoId(string s) {
  if(!YouTube(s)) return "";
  Uri u=new Uri(s); var m=Regex.Match(u.Query,@"(?:^\?|&)v=([A-Za-z0-9_-]{11})(?:&|$)");
  return u.AbsolutePath=="/watch" && m.Success ? m.Groups[1].Value : "";
 }
 static void Select(Tab t) {
  if(GetForegroundWindow().ToInt64()!=t.hwnd) SetForegroundWindow(new IntPtr(t.hwnd));
  var selection=(SelectionItemPattern)t.element.GetCurrentPattern(SelectionItemPattern.Pattern);
  if(selection.Current.IsSelected) return;
  selection.Select();
  for(int i=0;i<20;i++) {
   if(((SelectionItemPattern)t.element.GetCurrentPattern(SelectionItemPattern.Pattern)).Current.IsSelected) { Thread.Sleep(150); return; }
   Thread.Sleep(100);
  } throw new Exception("대상 탭 선택을 확인하지 못했습니다.");
 }
 static List<AutomationElement> Tabs(AutomationElement w) {
  var result=new List<AutomationElement>();
  foreach(AutomationElement e in w.FindAll(Desc,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.TabItem))) {
   try { if(!InPage(e)) result.Add(e); } catch(ElementNotAvailableException) {}
  }
  return result;
 }
 public static Inventory Scan() {
  var result=new Inventory();
  var windows=AutomationElement.RootElement.FindAll(TreeScope.Children,Condition.TrueCondition);
  foreach(AutomationElement w in windows) {
   string browser;
   try { browser=Process.GetProcessById(w.Current.ProcessId).ProcessName.ToLowerInvariant(); } catch { continue; }
   if(browser=="firefox" || browser=="opera") throw new Exception("열린 비지원 브라우저의 재생을 확인할 수 없습니다. 해당 브라우저를 정리한 뒤 다시 확인하세요.");
   if(browser!="chrome" && browser!="msedge" && browser!="brave") continue;
   if(w.Current.NativeWindowHandle==0) continue;
   var full=Button(Player(w),@"^(전체\s*화면 종료|Exit full screen)");
   if(full!=null) { Invoke(full); Thread.Sleep(400); }
   var tabs=Tabs(w);
   if(tabs.Count==0) throw new Exception("브라우저 탭 목록을 확인할 수 없습니다. 브라우저 전체화면(F11)을 해제하세요.");
   result.total_tabs+=tabs.Count;
   foreach(var e in tabs) {
    var t=new Tab {window=w,element=e,identity=Id(e),browser=browser,hwnd=w.Current.NativeWindowHandle};
    Select(t); t.url=URL(w); t.video_id=VideoId(t.url);
    if(YouTube(t.url)) result.tabs.Add(t);
   }
  }
  return result;
 }
 static bool Seconds(string text,out double seconds) {
  seconds=0; text=text.Trim();
  var colon=Regex.Match(text,@"^(?:(\d+):)?(\d{1,2}):(\d{2})$");
  if(colon.Success) {
   seconds=(colon.Groups[1].Success ? Double.Parse(colon.Groups[1].Value)*3600 : 0)+Double.Parse(colon.Groups[2].Value)*60+Double.Parse(colon.Groups[3].Value); return true;
  }
  var words=Regex.Match(text,@"^(?:(\d+)\s*(?:시간|hours?|hrs?)\s*)?(?:(\d+)\s*(?:분|minutes?|mins?)\s*)?(?:(\d+)\s*(?:초|seconds?|secs?))?$",RegexOptions.IgnoreCase);
  if(!words.Success || !(words.Groups[1].Success || words.Groups[2].Success || words.Groups[3].Success)) return false;
  for(int i=1;i<=3;i++) if(words.Groups[i].Success) seconds+=Double.Parse(words.Groups[i].Value)*(i==1?3600:i==2?60:1);
  return true;
 }
 public static bool IsPlayerError(string text) {
  return Regex.IsMatch(text??"",@"^(문제가 발생했습니다|오류가 발생했습니다|동영상을 재생할 수 없습니다|이 동영상을 재생할 수 없습니다|동영상을 볼 수 없습니다|이 동영상을 볼 수 없습니다|An error occurred|Something went wrong|Video unavailable|This video is unavailable|This video isn't available)",RegexOptions.IgnoreCase);
 }
 public static Observation Read(Tab t) {
  Select(t);
  var o=new Observation {url=URL(t.window),browser=t.browser,tab_id=t.identity,state="unknown"};
  o.video_id=VideoId(o.url);
  if(!YouTube(o.url)) throw new Exception("검사 중 탭의 주소가 바뀌었습니다. 명령을 중단합니다.");
  var p=Player(t.window);
  Last=o;
  if(p==null) { if(o.video_id=="") o.state="idle"; return o; }
  // Inspect only visible text inside this player, never surrounding page comments.
  var error=Find(p,e=>e.Current.ControlType==ControlType.Text && !e.Current.IsOffscreen && IsPlayerError(e.Current.Name));
  if(error!=null) { o.state="error"; o.player_error=error.Current.Name; return o; }
  // Keep the observed controls exposed; hidden Chromium controls can retain old
  // accessible time values. Focus is on a known player button, never a shortcut.
  var control=Button(p,PauseLabel) ?? Button(p,PlayLabel);
  if(control!=null && control.Current.IsKeyboardFocusable && !control.Current.HasKeyboardFocus) {
   control.SetFocus(); Thread.Sleep(100);
  }
  var doc=t.window.FindFirst(Desc,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Document));
  o.title=doc==null ? "" : Regex.Replace(doc.Current.Name,@"\s+- YouTube$","");
  o.playing=Button(p,PauseLabel)!=null;
  o.paused=Button(p,PlayLabel)!=null;
  var slider=Find(p,e=>e.Current.ControlType==ControlType.Slider && Regex.IsMatch(e.Current.Name,@"^(탐색 슬라이더|Seek slider)$",RegexOptions.IgnoreCase));
  if(slider!=null) {
   var range=((RangeValuePattern)slider.GetCurrentPattern(RangeValuePattern.Pattern)).Current;
   o.position=range.Value; o.duration=range.Maximum;
  }
  // Chromium sometimes leaves RangeValue stale; the player's time button is
  // updated independently. Prefer its complete, strictly parsed current/total.
  foreach(AutomationElement e in p.FindAll(Desc,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Button))) {
   try {
   var parts=e.Current.Name.Split('/'); double current,total;
   if(parts.Length==2 && Seconds(parts[0],out current) && Seconds(parts[1],out total) && total>0 && current<=total) { o.position=current; o.duration=total; break; }
   } catch(ElementNotAvailableException) {}
  }
  o.ad=Find(p,e=>!e.Current.IsOffscreen && Regex.IsMatch(e.Current.Name,@"^(광고(\s|$|·)|스폰서|건너뛰기|Skip ad|Sponsored|Ad\s*[·•0-9])",RegexOptions.IgnoreCase))!=null;
  o.state=o.ad ? "advertisement" : o.playing ? "playing" : o.paused ? "paused" : "unknown";
  Last=o;
  return o;
 }
 public static Observation Pause(Tab t) {
  Observation before=null;
  for(int i=0;i<15;i++) {
   try {
    before=Read(t);
    if(before.state=="error") throw new Exception("YOUTUBE_PLAYER_ERROR: "+before.player_error);
    if(before.state=="idle" || before.paused || before.playing) break;
   }
   catch(ElementNotAvailableException) {}
   Thread.Sleep(250);
  }
  if(before==null) throw new Exception("기존 유튜브 상태를 읽지 못했습니다.");
  if(before.state=="idle" || before.paused) return before;
  if(!before.playing) throw new Exception("기존 유튜브 재생 상태가 미확인입니다. 새 영상을 열지 않습니다.");
  Invoke(Button(Player(t.window),PauseLabel));
  for(int i=0;i<20;i++) { var o=Read(t); if(o.paused) return o; Thread.Sleep(150); }
  throw new Exception("기존 유튜브의 일시정지를 확인하지 못했습니다.");
 }
 public static void Navigate(Tab t,string url) {
  Select(t);
  if(!YouTube(URL(t.window))) throw new Exception("대상 탭이 유튜브에서 벗어났습니다.");
  var window=(WindowPattern)t.window.GetCurrentPattern(WindowPattern.Pattern);
  if(window.Current.WindowVisualState==WindowVisualState.Minimized) {
   window.SetWindowVisualState(WindowVisualState.Normal);
  }
  SetForegroundWindow(new IntPtr(t.hwnd));
  var address=Address(t.window); address.SetFocus();
  bool focused=false;
  for(int i=0;i<10;i++) {
   var element=AutomationElement.FocusedElement;
   if(GetForegroundWindow().ToInt64()==t.hwnd && element!=null && Id(element)==Id(address)) { focused=true; break; }
   Thread.Sleep(100);
  }
  if(!focused) throw new Exception("YOUTUBE_FOCUS_FAILED: 주소창 초점을 확인하지 못했습니다. 입력을 중단합니다.");
  ((ValuePattern)address.GetCurrentPattern(ValuePattern.Pattern)).SetValue(url);
  if(((ValuePattern)address.GetCurrentPattern(ValuePattern.Pattern)).Current.Value!=url) throw new Exception("주소 입력을 확인하지 못했습니다.");
  if(Id(AutomationElement.FocusedElement)!=Id(address)) throw new Exception("주소창 초점이 바뀌었습니다.");
  SendKeys.SendWait("{ENTER}");
 }
 public static void Play(Tab t) {
  try {
   var o=Read(t); var button=Button(Player(t.window),PlayLabel);
   if(o.paused && button!=null) Invoke(button);
  } catch(ElementNotAvailableException) { /* navigation: observe again, no blind key */ }
 }
 public static void Fullscreen(Tab t) {
  Select(t); var p=Player(t.window);
  if(Button(p,@"^(전체\s*화면 종료|Exit full screen)")!=null) return;
  Invoke(Button(p,@"^(전체\s*화면|Full screen)(\s*\(f\)|\s+키보드 단축키\s+f|\s+keyboard shortcut\s+f)$"));
  for(int i=0;i<20;i++) { if(Button(Player(t.window),@"^(전체\s*화면 종료|Exit full screen)")!=null) return; Thread.Sleep(100); }
  throw new Exception("전체화면 적용을 확인하지 못했습니다.");
 }
 public static bool Matches(Observation o,string video,string title,double duration) {
  return o.state!="error" && o.video_id==video && Normalize(o.title)==Normalize(title) && !o.ad &&
   duration>0 && Math.Abs(o.duration-duration)<=2 && o.playing;
 }
 public static string Failure(Observation o,string video,string title,double duration) {
  if(o.state=="error") return "YOUTUBE_PLAYER_ERROR: "+o.player_error;
  // Navigation and ads can expose stale metadata; only diagnose a loaded main video.
  if(o.video_id!=video || o.ad || o.duration<=0 || String.IsNullOrWhiteSpace(o.title)) return null;
  if(Normalize(o.title)!=Normalize(title)) return "YOUTUBE_TITLE_MISMATCH: 요청 제목=["+title+"] 실제 제목=["+o.title+"]. 검색 행의 전체 제목을 그대로 전달하세요.";
  if(Math.Abs(o.duration-duration)>2) return "YOUTUBE_DURATION_MISMATCH: 요청 길이="+duration+", 실제 길이="+o.duration+"초. 검색 행의 길이를 확인하세요.";
  return null;
 }
 static string Normalize(string s) { return Regex.Replace((s??"").Normalize(System.Text.NormalizationForm.FormKC),@"\s+"," ").Trim(); }
 static bool hoverOffset;
 static void ExposeControls(Tab t) {
  Select(t);
  // Keep controls on screen and hovered. YouTube stops updating accessible time
  // labels when its controls auto-hide, even though the video keeps playing.
  var window=(WindowPattern)t.window.GetCurrentPattern(WindowPattern.Pattern);
  if(window.Current.WindowVisualState!=WindowVisualState.Maximized) {
   window.SetWindowVisualState(WindowVisualState.Maximized); Thread.Sleep(250);
  }
  var control=Button(Player(t.window),PauseLabel) ?? Button(Player(t.window),PlayLabel);
  if(control==null) return; // navigation/ad may not have installed controls yet
  var rect=control.Current.BoundingRectangle;
  if(!control.Current.IsOffscreen && !rect.IsEmpty) {
   hoverOffset=!hoverOffset;
   var offset=Math.Min(3,rect.Width/4)*(hoverOffset?1:-1);
   SetCursorPos((int)(rect.X+rect.Width/2+offset),(int)(rect.Y+rect.Height/2));
   Thread.Sleep(150);
  }
 }
 public static Observation Verify(Tab t,string video,string title,double duration,int seconds) {
  var deadline=DateTime.UtcNow.AddSeconds(seconds);
  var lastSkip=DateTime.MinValue;
  Observation previous=null;
  string previousFailure=null;
  while(DateTime.UtcNow<deadline) {
   Observation o;
   try { ExposeControls(t); o=Read(t); }
   catch(ElementNotAvailableException) { previous=null; previousFailure=null; Thread.Sleep(250); continue; }
   var failure=Failure(o,video,title,duration);
   // Player errors are terminal. Metadata mismatches must repeat on two samples.
   if(failure!=null && (o.state=="error" || failure==previousFailure)) throw new Exception(failure);
   previousFailure=failure;
   if(o.video_id==video) {
    if(o.ad && (DateTime.UtcNow-lastSkip).TotalSeconds>3) {
     var skip=Button(Player(t.window),@"^((광고\s*)?건너뛰기|Skip( ads?)?)$");
     if(skip!=null && skip.Current.IsEnabled && !skip.Current.IsOffscreen) { Invoke(skip); lastSkip=DateTime.UtcNow; }
    }
    if(o.paused && failure==null) Play(t);
    if(Matches(o,video,title,duration)) {
     if(previous!=null && o.position>previous.position+0.25 && o.position-previous.position<10) { o.previous_position=previous.position; return o; }
     previous=o;
    } else previous=null;
   } else previous=null;
   Thread.Sleep(1000);
  }
  throw new Exception("YOUTUBE_PLAYBACK_TIMEOUT: 본영상 재생 진행을 확인하지 못했습니다. last_observation과 필요하면 화면을 한 번 확인하세요. 동일 요청을 재전송하지 마세요.");
 }
}
'@
    $result.hostname = $env:COMPUTERNAME
    $result.os_version = [Environment]::OSVersion.Version.ToString()
    $inventory = [PCYouTube]::Scan()
    $result.tab_count_before = $inventory.total_tabs
    $result.scope = '열려 있는 Chrome·Edge·Brave 창의 유튜브 탭'
    if ($PcRequest.action -eq 'youtube_status') {
        $result.tabs = @($inventory.tabs | ForEach-Object { [PCYouTube]::Read($_) })
        $result.verified = $true
        $result.message = '유튜브 탭의 플레이어 상태를 조회했습니다. 재생 완료 판정은 교체 요청의 검증을 사용합니다.'
    } elseif ($PcRequest.action -in @('youtube_replace','youtube_stop')) {
        if ($inventory.tabs.Count -eq 0) { throw 'YOUTUBE_NO_TAB: 열린 유튜브 탭이 없습니다. 사용할 브라우저에서 유튜브를 한 번 열어 주세요. 다른 작업 탭을 덮어쓰지 않습니다.' }
        $target = $inventory.tabs[0]
        if ($PcRequest.action -eq 'youtube_replace') {
            $video = [PCYouTube]::VideoId($PcRequest.url)
            if (-not $video -or -not $PcRequest.title -or $PcRequest.duration_seconds -le 0) { throw '영상 URL·제목·전체 길이가 필요합니다.' }
            foreach ($tab in $inventory.tabs) { if ($tab.video_id -eq $video) { $target = $tab; break } }
        }
        # Pause every existing player before any navigation, including the target.
        $result.before = @($inventory.tabs | ForEach-Object { [PCYouTube]::Pause($_) })
        $result.previous_stopped = $true
        if ($PcRequest.action -eq 'youtube_replace') {
            if ($target.video_id -ne $video) { [PCYouTube]::Navigate($target, $PcRequest.url) }
            $result.playback = [PCYouTube]::Verify($target, $video, $PcRequest.title, $PcRequest.duration_seconds, 60)
            $result.playback_verified = $true
        }
        # Re-enumerate: a concurrent new tab/player must not be silently ignored.
        $after = [PCYouTube]::Scan()
        $result.tab_count_after = $after.total_tabs
        if ($after.total_tabs -ne $inventory.total_tabs -or $after.tabs.Count -ne $inventory.tabs.Count) { throw '검증 중 탭 목록이 바뀌었습니다. 중복 재생 여부를 다시 확인하세요.' }
        if (@(Compare-Object @($inventory.tabs | ForEach-Object {$_.identity}) @($after.tabs | ForEach-Object {$_.identity})).Count -ne 0) { throw '검증 중 유튜브 탭의 신원이 바뀌었습니다.' }
        $result.tabs = @()
        foreach ($tab in $after.tabs) {
            if ($PcRequest.action -eq 'youtube_replace' -and $tab.identity -eq $target.identity) { continue }
            $observation = [PCYouTube]::Read($tab)
            $result.tabs += $observation
            if (-not $observation.paused -and $observation.state -ne 'idle') { throw '다른 유튜브 탭의 정지를 확인하지 못했습니다.' }
        }
        if ($PcRequest.action -eq 'youtube_replace') {
            $result.playback = [PCYouTube]::Verify($target, $video, $PcRequest.title, $PcRequest.duration_seconds, 10)
            if ($PcRequest.fullscreen) { [PCYouTube]::Fullscreen($target); $result.fullscreen_verified = $true }
        }
        $result.verified = $true
        $result.message = if ($PcRequest.action -eq 'youtube_replace') { '같은 유튜브 탭에서 본영상 재생과 다른 탭의 정지를 확인했습니다. 실제 스피커 소리는 별도 확인이 필요합니다.' } else { '열린 유튜브 탭의 재생 정지를 확인했습니다.' }
    } else { throw '지원하지 않는 유튜브 동작입니다.' }
    $result.success = $true
} catch {
    $result.success = $false; $result.verified = $false
    $cause = $_.Exception.GetBaseException()
    $result.error = if ($cause.Message) { $cause.Message } else { '브라우저 접근성 응답 실패: ' + $cause.GetType().Name }
    if ($result.error -match '^(YOUTUBE_[A-Z_]+):') { $result.error_code = $Matches[1] }
    $result.error_detail = $cause.ToString()
    if ('PCYouTube' -as [type]) { $result.last_observation = [PCYouTube]::Last }
} finally {
    $result.observed_at = [DateTime]::UtcNow.ToString('o')
    if ($locked) { $mutex.ReleaseMutex() }
    if ($null -ne $mutex) { $mutex.Dispose() }
}
Write-Output ('INDIEBIZ_PC_RESULT:' + (ConvertTo-Json -InputObject $result -Depth 8 -Compress))
