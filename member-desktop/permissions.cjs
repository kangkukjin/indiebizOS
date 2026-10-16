/* OS permission requests belong to the installed app, independently of any resident helper. */
function createPermissions({systemPreferences,desktopCapturer,shell},platform=process.platform){
 const status=()=>platform==='darwin'?{platform,screen:systemPreferences.getMediaAccessStatus('screen'),accessibility:systemPreferences.isTrustedAccessibilityClient(false)}:{platform,screen:'system-managed',accessibility:null};
 async function request(action='status'){
  if(!['status','screen','accessibility'].includes(action))throw Error('지원하지 않는 권한 요청입니다.');
  if(action==='status'||platform!=='darwin')return status();
  const before=status();
  if(action==='screen'?before.screen==='granted':before.accessibility)return before;
  let error='';
  if(action==='screen'){
   // Request through this app's identity. Never send this probe image to a hub.
   try{await desktopCapturer.getSources({types:['screen'],thumbnailSize:{width:1,height:1}});}catch(e){error=e.message;}
  }else systemPreferences.isTrustedAccessibilityClient(true);
  const current=status();
  if(action==='screen'?current.screen!=='granted':!current.accessibility){
   await shell.openExternal('x-apple.systempreferences:com.apple.preference.security?'+(action==='screen'?'Privacy_ScreenCapture':'Privacy_Accessibility'));
  }
  return {...current,...(error?{error}:{})};
 }
 return {status,request};
}
module.exports={createPermissions};
