const $=id=>document.getElementById(id);
let target=null,writeEnabled=false,busy=false;
function renderMode(){ $('mode').textContent=writeEnabled?'允许修改':'只读模式';$('permission').textContent=writeEnabled?'恢复只读':'开启修改';for(const button of document.querySelectorAll('button'))button.disabled=busy||(button.hasAttribute('data-write')&&!writeEnabled); }
async function rpc(action,input={}){
 if(typeof eda==='undefined')throw new Error('请在嘉立创 EDA 内安装并打开本扩展。');
 const result=await eda.sys_MessageBus.rpcCall('easyeda-mcp:request',{action,input},960000);
 if(!result||result.ok!==true)throw new Error(JSON.stringify(result?.error??'没有收到扩展响应'));
 return result.data;
}
async function refresh(){
 writeEnabled=(await rpc('getCapabilities')).writeEnabled;
 const info=await rpc('inspectProject');
 target=info.status==='read'?{projectUuid:info.project.uuid,documentUuid:info.currentDocument.uuid}:null;
 $('project').textContent=info.project?.friendlyName??info.project?.name??(info.project?'工程（名称暂不可用）':'当前没有打开工程');$('document').textContent=info.currentDocument?.title??info.currentDocument?.name??(target?info.currentDocument.uuid:'尚未打开图页');$('project-id').textContent=info.project?.uuid??'—';$('document-id').textContent=info.currentDocument?.uuid??'—';return info;
}
async function run(action,format){
 if(busy)return;busy=true;renderMode();$('status').textContent='执行中…';
 try{
  let result;
  if(action==='refresh')result=await refresh();
  else if(action==='permission'){const state=await rpc(writeEnabled?'disableWrites':'enableWrites');writeEnabled=state.writeEnabled;result=state;}
  else{if(!target)throw new Error('先打开目标工程和图页，再刷新工程。');result=await rpc(action,{...target,...(format?{formats:[format],delivery:'dialog'}:{})});}
  $('result').textContent=JSON.stringify(result,null,2);$('status').textContent='已返回结果';
 }catch(error){$('result').textContent=String(error);$('status').textContent='操作未完成';}
 finally{busy=false;renderMode();}
}
$('refresh').onclick=()=>run('refresh');$('permission').onclick=()=>run('permission');
for(const button of document.querySelectorAll('[data-action]'))button.onclick=()=>run(button.dataset.action);
for(const button of document.querySelectorAll('[data-format]'))button.onclick=()=>run('exportManufacturing',button.dataset.format);
(async()=>{try{writeEnabled=(await rpc('getCapabilities')).writeEnabled;renderMode();await run('refresh');}catch(error){$('mode').textContent='未连接';$('result').textContent=String(error);}})();
