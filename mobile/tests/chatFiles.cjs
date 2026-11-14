const ts=require('typescript'),fs=require('node:fs'),assert=require('node:assert/strict'),{test}=require('node:test');
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,f);
test('native file selection admits only web-supported local files and matching media types',()=>{
 const {validateChatFile}=require('../src/chatFiles.ts');
 for(const [name,type,kind] of [['scan.png','image/png','IMAGE'],['report.pdf','application/pdf','FILE'],['recording.m4a','audio/mp4','VOICE'],['recording.mp3','audio/mpeg','VOICE'],['recording.wav','audio/wav','VOICE'],['recording.ogg','audio/ogg','VOICE']])assert.equal(validateChatFile({uri:'file:///cache/x',name,type,size:10}).kind,kind);
 for(const file of [{uri:'https://external.invalid/x',name:'x.jpg',type:'image/jpeg',size:10},{uri:'file:///x',name:'x.exe',type:'application/octet-stream',size:10},{uri:'file:///x',name:'x.jpg',type:'application/pdf',size:10},{uri:'file:///x',name:'x.png',type:'image/png',size:16*1024*1024},{uri:'file:///x',name:'x.pdf',type:'application/pdf',size:26*1024*1024}])assert.throws(()=>validateChatFile(file));
});
test('image edit geometry stays within the image and export preserves aspect ratio',()=>{
 const {fitChatImage,clampChatPoint}=require('../src/chatFiles.ts');
 assert.deepEqual(fitChatImage(1600,800,300,400),{width:300,height:150,exportWidth:1600,exportHeight:800});
 assert.deepEqual(fitChatImage(800,1600,300,400),{width:200,height:400,exportWidth:800,exportHeight:1600});
 assert.deepEqual(clampChatPoint(-12,900,300,150),[0,150]);
 assert.throws(()=>fitChatImage(0,800,300,400));
});
