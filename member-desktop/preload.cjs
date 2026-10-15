const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('DesktopMember',Object.freeze({
  onDisconnected:(callback)=>ipcRenderer.on('member:disconnected',()=>callback()),
  setup:()=>ipcRenderer.invoke('member:setup'),
  enroll:(hub,code)=>ipcRenderer.invoke('member:enroll',{hub,code}),
  request:(path,body)=>ipcRenderer.invoke('member:request',{path,body}),
  chooseWorkspace:()=>ipcRenderer.invoke('member:folder'),
  openFile:(taskId,path,reveal=false)=>ipcRenderer.invoke('member:open',{taskId,path,reveal}),
  saveDiagnostics:()=>ipcRenderer.invoke('member:diagnostics'),
  settings:()=>ipcRenderer.invoke('member:settings'),
  disconnect:()=>ipcRenderer.invoke('member:disconnect'),
  startup:(enabled)=>ipcRenderer.invoke('member:startup',Boolean(enabled)),
  importArchive:()=>ipcRenderer.invoke('member:import'),
}));
