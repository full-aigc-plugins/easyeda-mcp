import {test} from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import vm from 'node:vm';

async function fixture(){
 const registry=new Map(),calls=[],services=new Map();let accepted=false;
 const api={
  sys_ExternalApi:{register:(namespace,name,fn,help)=>{assert.equal(namespace,'easyedaMcp');registry.set(name,{fn,help});calls.push('register')}},
  sys_MessageBus:{rpcService:(topic,fn)=>services.set(topic,fn)},
  sys_Dialog:{showConfirmationMessage:(a,b,c,d,fn)=>fn(accepted),showInformationMessage:()=>{}},
  sys_IFrame:{openIFrame:async(...args)=>{calls.push(args);return true}},
  dmt_Project:{getCurrentProjectInfo:async()=>undefined},dmt_SelectControl:{getCurrentDocumentInfo:async()=>undefined},
  pcb_Document:{autoLayout:async()=>{},autoRouting:async()=>{}}
 };
 const result=await build({entryPoints:['src/index.ts'],bundle:true,platform:'browser',format:'iife',globalName:'extension',write:false,metafile:true});
 const context={setTimeout,clearTimeout,eda:api,console:{error:()=>{},warn:()=>{}}};
 vm.runInNewContext(result.outputFiles[0].text,context);
 return {extension:context.extension,registry,calls,services,accept:()=>accepted=true,metafile:result.metafile};
}
test('激活只注册 14 个上层接口，重复激活不重复注册',async()=>{
 const f=await fixture();f.extension.activate();f.extension.activate();assert.equal(f.registry.size,14);assert.equal(f.calls.length,14);
 for(const [name,{help}] of f.registry){assert.ok(help.title);assert.ok(help.params);assert.match(help.example,new RegExp(name));}
 assert.ok(f.services.has('easyeda-mcp:request'));
});
test('真实浏览器 bundle 的空工程响应与错误封装',async()=>{
 const f=await fixture();f.extension.activate();const r=await f.registry.get('inspectProject').fn({});assert.equal(r.ok,true);assert.equal(r.data.status,'no_project');
 const blocked=await f.registry.get('autoRoute').fn({});assert.equal(blocked.ok,false);assert.equal(blocked.error.code,'READ_ONLY');
});
test('用户取消确认保持只读，确认后才开启，随后可关闭',async()=>{
 const f=await fixture();f.extension.activate();await f.extension.enableWrites();assert.equal((await f.registry.get('getCapabilities').fn({})).data.writeEnabled,false);
 f.accept();await f.extension.enableWrites();assert.equal((await f.registry.get('getCapabilities').fn({})).data.writeEnabled,true);
 f.extension.disableWrites();assert.equal((await f.registry.get('getCapabilities').fn({})).data.writeEnabled,false);
});
test('面板入口指向包内绝对 iframe 路径且主动打开',async()=>{
 const f=await fixture();assert.equal(f.calls.length,0);await f.extension.openPanel();assert.equal(f.calls.at(-1)[0],'/iframe/index.html');
});
test('主进程 bundle 不捆绑 Node 或 UI DOM 依赖',async()=>{
 const f=await fixture();assert.ok(Object.keys(f.metafile.inputs).every(name=>!name.includes('node_modules')&&!name.includes('iframe/')));
});
