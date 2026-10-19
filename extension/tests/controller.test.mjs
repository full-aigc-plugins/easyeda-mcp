import {before, test} from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {createRequire} from 'node:module';
import {mkdir} from 'node:fs/promises';
const require=createRequire(import.meta.url);
let createController;
before(async()=>{
  await mkdir('../.local/tests',{recursive:true});
  await build({entryPoints:['src/controller.ts'],bundle:true,platform:'node',format:'cjs',outfile:'../.local/tests/controller.cjs'});
  ({createController}=require('../../.local/tests/controller.cjs'));
});

function fixture() {
  const calls=[];
  const doc={uuid:'d1',documentType:3,parentProjectUuid:'p1'};
  const primitive=(id='c1')=>({getState_PrimitiveId:()=>id,getState_Designator:()=> 'U1',getState_X:()=>100,getState_Y:()=>200,getState_Rotation:()=>0,
    toAsync(){return this},setState_Designator(){return this},done:async()=>primitive(id)});
  const api={
    dmt_Project:{getCurrentProjectInfo:async()=>({uuid:'p1',name:'Test'})},
    dmt_SelectControl:{getCurrentDocumentInfo:async()=>({...doc})},
    dmt_Board:{getAllBoardsInfo:async()=>[]},dmt_Schematic:{getAllSchematicPagesInfo:async()=>[]},dmt_Pcb:{getAllPcbsInfo:async()=>[]},
    pcb_Document:{autoLayout:async()=>{calls.push('layout');return{}},autoRouting:async(props)=>{calls.push(props);return {failedNets:['GND'],totalNets:3,routedNets:2}},save:async()=>true},
    pcb_Drc:{check:async()=>[{message:'clearance'}]},sch_Drc:{check:async()=>[]},
    pcb_PrimitiveComponent:{getAll:async()=>[primitive()],create:async()=>{calls.push('pcb-create');return primitive()}},
    sch_PrimitiveComponent:{getAll:async()=>[primitive()],create:async()=>{calls.push('sch-create');return primitive()},getAllPinsByPrimitiveId:async(id)=>[
      {getState_PinNumber:()=> '1',getState_PinName:()=> 'IO',getState_X:()=>id==='a'?10:30,getState_Y:()=>id==='a'?20:40,getState_Rotation:()=>0,getState_NoConnected:()=>false}]},
    sch_PrimitiveWire:{create:async(points,net)=>{calls.push({points,net});return primitive('w1')}},
    sch_ManufactureData:{getNetlistFile:async()=>new File(['NET-DATA'],'net.enet')},
    pcb_ManufactureData:{getGerberFile:async()=>undefined,getBomFile:async()=>new File(['ABCD'],'Board.csv'),getPickAndPlaceFile:async()=>new File(['POS'],'Board.csv')},
    sys_FileSystem:{saveFile:async()=>{},saveFileToFileSystem:async(...args)=>{calls.push(args);return false}},
    lib_Device:{search:async()=>[]}
  };
  return {api,calls,doc};
}
const target={projectUuid:'p1',documentUuid:'d1'};

test('空工程明确返回 no_project，不创建或打开工程',async()=>{
 const f=fixture();f.api.dmt_Project.getCurrentProjectInfo=async()=>undefined;f.api.dmt_SelectControl.getCurrentDocumentInfo=async()=>undefined;
 const result=await createController(f.api).inspectProject({});assert.equal(result.status,'no_project');assert.deepEqual(f.calls,[]);
});
test('工程已打开但未激活图页时仍可读取工程目录',async()=>{
 const f=fixture();f.api.dmt_SelectControl.getCurrentDocumentInfo=async()=>undefined;
 const r=await createController(f.api).inspectProject({});assert.equal(r.status,'project_only');assert.equal(r.project.uuid,'p1');assert.equal(r.currentDocument,null);assert.deepEqual(r.pcbs,[]);
});
test('默认只读，不能通过参数开启写入',async()=>{
 const f=fixture();await assert.rejects(()=>createController(f.api).autoRoute({...target,writeEnabled:true}),e=>e.code==='READ_ONLY');assert.deepEqual(f.calls,[]);
});
test('文档 UUID 不匹配时不布线',async()=>{
 const f=fixture();await assert.rejects(()=>createController(f.api,{writeEnabled:true}).autoRoute({...target,documentUuid:'other'}),e=>e.code==='TARGET_CHANGED');assert.deepEqual(f.calls,[]);
});
test('自动布线保留 failedNets，使用 SDK 的 RoutingNets 字段',async()=>{
 const f=fixture();const r=await createController(f.api,{writeEnabled:true}).autoRoute({...target,nets:['GND']});assert.deepEqual(r.result.failedNets,['GND']);assert.deepEqual(f.calls[0],{RoutingNets:['GND']});
});
test('DRC 违规不被转成通过',async()=>{
 const r=await createController(fixture().api).checkDrc(target);assert.equal(r.passed,false);assert.equal(r.total,1);
});
test('器件创建前验证整个批次，后续坏坐标不能造成部分写入',async()=>{
 const f=fixture();f.doc.documentType=1;
 await assert.rejects(()=>createController(f.api,{writeEnabled:true}).placeSchematicComponents({...target,components:[{libraryUuid:'l',deviceUuid:'u',x:1,y:1},{libraryUuid:'l',deviceUuid:'u',x:'bad',y:2}]}),e=>e.code==='BAD_INPUT');assert.deepEqual(f.calls,[]);
});
test('连线用真实引脚端点并生成正交路径',async()=>{
 const f=fixture();f.doc.documentType=1;
 await createController(f.api,{writeEnabled:true}).connectPins({...target,from:{primitiveId:'a',pinNumber:'1'},to:{primitiveId:'b',pinNumber:'1'},netName:'SIG'});
 assert.deepEqual(f.calls,[{points:[10,20,30,20,30,40],net:'SIG'}]);
});
test('网表文本分页保留总长度和下一页位置',async()=>{
 const f=fixture();f.doc.documentType=1;const r=await createController(f.api).getNetlist({...target,offset:0,limit:3});assert.equal(r.text,'NET');assert.equal(r.nextOffset,3);assert.equal(r.totalCharacters,8);
});
test('制造文件 undefined 不算导出成功',async()=>{
 const f=fixture();await assert.rejects(()=>createController(f.api).exportManufacturing({...target,formats:['gerber'],delivery:'base64'}),e=>e.code==='EXPORT_FAILED');
});
test('base64 导出实际字节，保持文件名和大小',async()=>{
 const f=fixture();const r=await createController(f.api).exportManufacturing({...target,formats:['bom'],delivery:'base64'});assert.equal(r.files[0].bytes,4);assert.equal(Buffer.from(r.files[0].base64,'base64').toString(),'ABCD');
});
test('文件系统返回 false 时报告失败且不设置 force=true',async()=>{
 const f=fixture();await assert.rejects(()=>createController(f.api).exportManufacturing({...target,formats:['bom'],delivery:'filesystem',outputDirectory:'/tmp/output'}),e=>e.code==='EXPORT_FAILED');assert.equal(f.calls[0][3],false);
});
test('拒绝空批次和越界分页',async()=>{
 const f=fixture();await assert.rejects(()=>createController(f.api).listComponents({...target,limit:10000}),e=>e.code==='BAD_INPUT');
});
test('文件保存后必须回读实际字节，不能只相信 true',async()=>{
 const f=fixture();f.api.sys_FileSystem.saveFileToFileSystem=async()=>true;
 f.api.sys_FileSystem.readFileFromFileSystem=async()=>new File(['WRONG'],'Board.csv');
 await assert.rejects(()=>createController(f.api).exportManufacturing({...target,formats:['bom'],delivery:'filesystem',outputDirectory:'/tmp/output'}),e=>e.code==='EXPORT_FAILED'&&e.partial[0].status==='saved_unverified');
});
test('文件保存且字节一致才报告 saved',async()=>{
 const f=fixture();f.api.sys_FileSystem.saveFileToFileSystem=async()=>true;
 f.api.sys_FileSystem.readFileFromFileSystem=async()=>new File(['ABCD'],'Board.csv');
 const r=await createController(f.api).exportManufacturing({...target,formats:['bom'],delivery:'filesystem',outputDirectory:'/tmp/output'});
 assert.equal(r.files[0].status,'saved');assert.equal(r.files[0].byteVerified,true);
});
test('SDK 创建导线返回 undefined 要报告未确认',async()=>{
 const f=fixture();f.doc.documentType=1;f.api.sch_PrimitiveWire.create=async()=>undefined;
 await assert.rejects(()=>createController(f.api,{writeEnabled:true}).connectPins({...target,from:{primitiveId:'a',pinNumber:'1'},to:{primitiveId:'b',pinNumber:'1'},netName:'SIG'}),e=>e.code==='CREATE_FAILED');
});
test('批次中途失败保留已创建对象，不自动再次创建',async()=>{
 const f=fixture();f.doc.documentType=1;const original=f.api.sch_PrimitiveComponent.create;let count=0;
 f.api.sch_PrimitiveComponent.create=async()=>{if(++count===2)throw new Error('SDK failed');return original()};
 await assert.rejects(()=>createController(f.api,{writeEnabled:true}).placeSchematicComponents({...target,components:[{libraryUuid:'l',deviceUuid:'u',x:1,y:1},{libraryUuid:'l',deviceUuid:'u',x:2,y:2}]}),e=>e.code==='PARTIAL_CHANGE'&&e.partial[0].primitiveId==='c1');assert.equal(count,2);
});

test('工程信息 API 挂起时只读可使用活动图页真实父工程 UUID',{timeout:8000},async()=>{
 const f=fixture();f.api.dmt_Project.getCurrentProjectInfo=()=>new Promise(()=>{});
 const r=await createController(f.api).inspectProject({});assert.equal(r.status,'read');assert.equal(r.project.uuid,'p1');assert.equal(r.projectInfoSource,'active_document');assert.ok(r.warnings.length);
 const list=await createController(f.api).listComponents(target);assert.equal(list.total,1);
});
test('工程身份无法完整校验时不能自动布局',{timeout:4000},async()=>{
 const f=fixture();f.api.dmt_Project.getCurrentProjectInfo=()=>new Promise(()=>{});
 await assert.rejects(()=>createController(f.api,{writeEnabled:true}).autoLayout(target),e=>e.code==='SDK_TIMEOUT');assert.deepEqual(f.calls,[]);
});
