const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const ts=require('typescript');
require.extensions['.ts']=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,filename);
const {evaluateVoiceDeviceCheck,isPrivateVoiceDeviceCheckUri,removePrivateVoiceDeviceCheckFile,isPrivateVoiceDeviceCheckCacheChildUri,removePrivateVoiceDeviceCheckCacheChildFile,voiceDeviceSignalLevel,stopVoiceDeviceRecorderVerified,VOICE_DEVICE_CHECK_DURATION_MS,VOICE_DEVICE_CHECK_MIN_DURATION_MS,VOICE_DEVICE_CHECK_MIN_SIGNAL_DB}=require('../src/voiceDeviceCheck.ts');

test('native microphone check uses the same six-second preparation window as web',()=>{
 assert.equal(VOICE_DEVICE_CHECK_DURATION_MS,6000);
 assert.equal(VOICE_DEVICE_CHECK_MIN_DURATION_MS,5500);
});

test('temporary microphone file must be a direct M4A child of the app cache',()=>{
 const cache='file:///data/user/0/example/cache/';
 assert.equal(isPrivateVoiceDeviceCheckUri(cache+'Audio-123456.m4a',cache),true);
 assert.equal(isPrivateVoiceDeviceCheckUri(cache+'../files/Audio-123456.m4a',cache),false);
 assert.equal(isPrivateVoiceDeviceCheckUri('file:///data/user/0/example/cache-evil/Audio.m4a',cache),false);
 assert.equal(isPrivateVoiceDeviceCheckUri(cache+'nested/Audio.m4a',cache),false);
 assert.equal(isPrivateVoiceDeviceCheckUri('/tmp/Audio.m4a',cache),false);
});

test('verified cleanup succeeds only after the cache file is absent',async()=>{
 const cache='file:///data/user/0/example/cache/',path=cache+'Audio-123456.m4a';
 let exists=true,deletes=0;
 const fileSystem={getInfoAsync:async()=>({exists}),deleteAsync:async(uri,options)=>{assert.equal(uri,path);assert.deepEqual(options,{idempotent:true});deletes++;exists=false;}};
 assert.equal(await removePrivateVoiceDeviceCheckFile(path,cache,fileSystem),true);
 assert.equal(deletes,1);
 assert.equal(await removePrivateVoiceDeviceCheckFile(path,cache,fileSystem),true,'already absent is idempotently clean');
});

test('delete errors or a file that remains are not accepted as cleanup',async()=>{
 const cache='file:///data/user/0/example/cache/',path=cache+'Audio-123456.m4a';
 assert.equal(await removePrivateVoiceDeviceCheckFile(path,cache,{getInfoAsync:async()=>({exists:true}),deleteAsync:async()=>{throw Error('denied')}}),false);
 assert.equal(await removePrivateVoiceDeviceCheckFile(path,cache,{getInfoAsync:async()=>({exists:true}),deleteAsync:async()=>{}}),false);
});

test('invalid paths are never sent to the filesystem delete operation',async()=>{
 let deletes=0;
 const cache='file:///data/user/0/example/cache/';
 assert.equal(await removePrivateVoiceDeviceCheckFile(cache+'../files/Audio.m4a',cache,{getInfoAsync:async()=>({exists:true}),deleteAsync:async()=>{deletes++;}}),false);
 assert.equal(deletes,0);
});
test('unexpected recorder artifacts are cleaned only as direct private-cache children',async()=>{
 const cache='file:///data/user/0/example/cache/',safe=cache+'unexpected.tmp',outside='file:///data/user/0/example/files/record.m4a';
 let safeExists=true,outsideExists=true,deletes=0;
 const fileSystem={getInfoAsync:async uri=>({exists:uri===safe?safeExists:outsideExists}),deleteAsync:async uri=>{deletes++;if(uri===safe)safeExists=false;else outsideExists=false;}};
 assert.equal(isPrivateVoiceDeviceCheckCacheChildUri(safe,cache),true);
 assert.equal(isPrivateVoiceDeviceCheckCacheChildUri(cache+'../files/record.m4a',cache),false);
 assert.equal(await removePrivateVoiceDeviceCheckCacheChildFile(safe,cache,fileSystem),true);
 assert.equal(safeExists,false);
 assert.equal(await removePrivateVoiceDeviceCheckCacheChildFile(outside,cache,fileSystem),false);
 assert.equal(outsideExists,true);
 assert.equal(deletes,1);
});

test('unverified temporary-file cleanup never reports a passed microphone check',()=>{
 assert.equal(evaluateVoiceDeviceCheck({permissionGranted:true,durationMs:6000,fileBytes:1024,peakMeteringDb:-5,cleanupVerified:false}),'cleanup_failed');
 assert.equal(evaluateVoiceDeviceCheck({permissionGranted:true,durationMs:6000,fileBytes:1024,peakMeteringDb:-5,cleanupVerified:true}),'passed');
});

test('audio-mode restoration failure is distinct from capture success and cleanup failure',()=>{
 const captured={permissionGranted:true,durationMs:6000,fileBytes:1024,peakMeteringDb:-5};
 assert.equal(evaluateVoiceDeviceCheck({...captured,audioModeRestored:false}),'audio_mode_restore_failed');
 assert.equal(evaluateVoiceDeviceCheck({...captured,audioModeRestored:true}),'passed');
 assert.equal(evaluateVoiceDeviceCheck(captured),'passed','older callers without an audio-mode result retain the established contract');
 assert.equal(evaluateVoiceDeviceCheck({...captured,cleanupVerified:false,audioModeRestored:false}),'cleanup_failed','unverified private-file cleanup keeps the higher-priority privacy warning');
});

test('permission denial never reports a successful microphone check',()=>{
 assert.equal(evaluateVoiceDeviceCheck({permissionGranted:false,durationMs:6000,fileBytes:1024,peakMeteringDb:-5}),'permission_denied');
});

test('short capture is incomplete even when a temporary file exists',()=>{
 assert.equal(evaluateVoiceDeviceCheck({permissionGranted:true,durationMs:5499,fileBytes:1024,peakMeteringDb:-5}),'capture_incomplete');
});

test('empty or missing temporary audio is not accepted',()=>{
 assert.equal(evaluateVoiceDeviceCheck({permissionGranted:true,durationMs:6000,fileBytes:0,peakMeteringDb:-5}),'no_audio_file');
});

test('missing native metering no longer fails a valid capture',()=>{
 assert.equal(evaluateVoiceDeviceCheck({permissionGranted:true,durationMs:6000,fileBytes:1024,peakMeteringDb:null}),'passed');
});

test('quiet input is distinguished from a working microphone signal',()=>{
 assert.equal(evaluateVoiceDeviceCheck({permissionGranted:true,durationMs:6000,fileBytes:1024,peakMeteringDb:-55}),'low_signal');
});

test('a complete local capture with measurable signal passes',()=>{
 assert.equal(evaluateVoiceDeviceCheck({permissionGranted:true,durationMs:6000,fileBytes:1024,peakMeteringDb:VOICE_DEVICE_CHECK_MIN_SIGNAL_DB}),'passed');
});

test('meter display is bounded for silence, normal speech and clipped input',()=>{
 assert.equal(voiceDeviceSignalLevel(null),0);
 assert.equal(voiceDeviceSignalLevel(-160),0);
 assert.ok(voiceDeviceSignalLevel(-30)>0&&voiceDeviceSignalLevel(-30)<1);
 assert.equal(voiceDeviceSignalLevel(5),1);
});


test('device preflight treats recorder stop as successful only after Expo reports inactive',async()=>{
 const calls=[];
 const stopped=await stopVoiceDeviceRecorderVerified({
  stop:async()=>{calls.push('stop')},
  getStatus:()=>({isRecording:false})
 });
 assert.equal(stopped,true);
 assert.deepEqual(calls,['stop']);
 assert.equal(await stopVoiceDeviceRecorderVerified({
  stop:async()=>{throw Error('native stop rejected')},
  getStatus:()=>({isRecording:false})
 }),false,'a rejected stop is not accepted merely because a later snapshot looks inactive');
 assert.equal(await stopVoiceDeviceRecorderVerified({
  stop:async()=>{},
  getStatus:()=>({isRecording:true})
 }),false,'a resolved stop with a still-recording snapshot remains unsafe');
 assert.equal(await stopVoiceDeviceRecorderVerified({
  stop:async()=>{},
  getStatus:()=>({})
 }),false,'missing status is inconclusive');
 assert.equal(await stopVoiceDeviceRecorderVerified({
  stop:async()=>{},
  getStatus:()=>{throw Error('status unavailable')}
 }),false,'status read failure is inconclusive');
});
