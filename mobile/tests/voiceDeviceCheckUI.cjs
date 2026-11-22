const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const component=fs.readFileSync(path.join(__dirname,'../src/NativeVoiceDeviceCheck.tsx'),'utf8');
const helper=fs.readFileSync(path.join(__dirname,'../src/voiceDeviceCheck.ts'),'utf8');
const entry=fs.readFileSync(path.join(__dirname,'../src/VoiceExamEntry.tsx'),'utf8');

test('native device check mirrors the six-second local preparation flow',()=>{
 assert.match(component,/VOICE_DEVICE_CHECK_DURATION_MS/);
 assert.match(component,/requestRecordingPermissionsAsync/);
 assert.match(component,/isMeteringEnabled:true/);
 assert.match(component,/useAudioRecorderState\(recorder,100\)/);
});

test('microphone test uses only temporary app cache and deletes the file after stop',()=>{
 assert.match(component,/directory:'cache'/);
 assert.match(component,/FileSystem\.cacheDirectory/);
 assert.match(component,/removePrivateVoiceDeviceCheckFile\(path,FileSystem\.cacheDirectory,FileSystem\)/);
 assert.match(helper,/await fileSystem\.deleteAsync\(uri,\{idempotent:true\}\)/);
 assert.match(component,/stopVoiceDeviceRecorderVerified\(recorder\)/);
 assert.match(helper,/await recorder\.stop\(\)/,'the recorder stop is owned by the verified lifecycle helper');
 assert.match(helper,/recorder\.getStatus\(\)\.isRecording===false/,'stop requires an explicit inactive Expo status');
 assert.doesNotMatch(component,/await recorder\.stop\(\)/,'the UI must not bypass the verified stop helper');
 assert.doesNotMatch(component,/documentDirectory|SecureStore|AsyncStorage/);
});

test('microphone test verifies cache-file deletion and keeps a retry path on failure',()=>{
 assert.match(component,/isPrivateVoiceDeviceCheckUri\(path,cache\)/);
 assert.match(component,/removePrivateVoiceDeviceCheckFile\(path,FileSystem\.cacheDirectory,FileSystem\)/);
 assert.match(helper,/await fileSystem\.deleteAsync\(uri,\{idempotent:true\}\)/);
 assert.match(helper,/const after=await fileSystem\.getInfoAsync\(uri\)/);
 assert.match(helper,/return after\.exists!==true/);
 assert.match(component,/if\(cleanupVerified\)uri\.current=null/);
 assert.match(component,/setCleanupPending\(!cleanupVerified\)/);
 assert.match(component,/async function retryCleanup\(\)/);
 assert.match(component,/Geçici ses dosyasını silmeyi yeniden dene/);
 assert.match(component,/cleanupVerified,audioModeRestored\}\)/);
});
test('unexpected recorder URIs are retained for safe cleanup before the next microphone test',()=>{
 const capture=component.indexOf('const path=recorder.uri;');
 const retained=component.indexOf("if(typeof path==='string'&&path)uri.current=path;",capture);
 const validated=component.indexOf('if(!path||!cache||!isPrivateVoiceDeviceCheckUri(path,cache))',capture);
 assert.ok(capture>=0&&retained>capture&&validated>retained,'the returned URI is retained before strict validation can throw');
 assert.match(component,/removePrivateVoiceDeviceCheckCacheChildFile/);
 assert.match(component,/setCleanupPending\(!cleanupVerified\)/);
 assert.match(component,/cleanupPending\|\|audioModeBlocked/);
});

test('device preflight fails closed when app-wide playback audio mode cannot be restored',()=>{
 assert.match(component,/restoreVoiceAudioMode/);
 assert.match(component,/async function resetAudioMode\(\):Promise<boolean>/);
 assert.match(component,/if\(mounted\.current\)setAudioModeBlocked\(!restored\)/);
 assert.match(component,/audioModeRestored=await resetAudioMode\(\)/);
 assert.match(component,/audio_mode_restore_failed/);
 assert.match(component,/audioModeBlocked\|\|uri\.current!==null/);
 assert.match(component,/\(stopPending\|\|cleanupPending\|\|audioModeBlocked\)&&<Pressable/);
 assert.match(component,/Cihaz ses yönlendirmesini yeniden dene/);
 assert.doesNotMatch(component,/setAudioModeAsync\(\{allowsRecording:false\}\)\.catch\(\(\)=>\{\}\)/);
});

test('microphone test never sends audio, patient identity or transcript to an API',()=>{
 assert.doesNotMatch(component,/\bfetch\s*\(|axios|FormData|transcribeNativeRecording|voiceApi|patientId|userId|transcript|token/);
});

test('backgrounding and leaving the screen cancel the test and close the recorder',()=>{
 assert.match(component,/AppState\.addEventListener/);
 assert.match(component,/if\(state!=='active'&&running\.current\)/);
 assert.match(component,/useIsFocused\(\)/);
 assert.match(component,/if\(!focused&&running\.current\)/);
 assert.match(component,/cancelRef\.current/);
});

test('voice examination exposes the check before consent and blocks conflicting clinical actions',()=>{
 assert.match(entry,/NativeVoiceDeviceCheck disabled=\{processing\|\|audioBusy\|\|deviceCheckBusy\|\|applyBusy\}/);
 assert.match(entry,/onBusyChange=\{setDeviceCheckBusy\}/);
 assert.match(entry,/usePreventRemove\(processing\|\|audioBusy\|\|deviceCheckBusy\|\|applyBusy/);
 assert.match(entry,/disabled=\{processing\|\|applyBusy\|\|deviceCheckBusy\} onBusyChanged=\{setAudioBusy\}/);
});


test('an unverified microphone stop keeps the recorder and private file intact until retry',()=>{
 const finish=component.indexOf('async function finish(run:number)');
 const finishStop=component.indexOf('const stopped=await stopPreparedRecorder()',finish);
 const finishCleanup=component.indexOf('removeTemporaryFile(path)',finish);
 assert.ok(finish>=0&&finishStop>finish&&finishCleanup>finishStop,'finish verifies stop before attempting file cleanup');
 assert.match(component.slice(finishStop,finishCleanup),/if\(!stopped\)[\s\S]*setStopPending\(true\)[\s\S]*notifyBusy\(true\)[\s\S]*return/);
 const cancel=component.indexOf('async function cancel(');
 const cancelStop=component.indexOf('await stopPreparedRecorder()',cancel);
 const cancelCleanup=component.indexOf('removeTemporaryFile(uri.current)',cancel);
 assert.ok(cancelStop>cancel&&cancelCleanup>cancelStop,'cancel verifies stop before deleting the temporary file');
 const retry=component.indexOf('async function retryCleanup()');
 const retryStop=component.indexOf('await stopPreparedRecorder()',retry);
 const retryCleanup=component.indexOf('removeTemporaryFile(path)',retry);
 assert.ok(retryStop>retry&&retryCleanup>retryStop,'retry also stops and verifies before cleanup');
 assert.match(component,/if\(disabled\|\|stopPending\|\|cleanupPending\|\|audioModeBlocked/);
 assert.match(component,/\(stopPending\|\|cleanupPending\|\|audioModeBlocked\)&&<Pressable/);
 assert.match(component,/disabled=\{busyPhase\} onPress=\{\(\)=>void retryCleanup\(\)\}/,'the recovery control stays usable while the parent blocks conflicting voice actions');
 const preparedClears=[...component.matchAll(/prepared\.current=false/g)];
 assert.equal(preparedClears.length,1,'prepared state is cleared only by the verified-stop helper');
 assert.match(component,/if\(stopped\)prepared\.current=false/);
});
