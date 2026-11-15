const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const component=fs.readFileSync(path.join(__dirname,'../src/NativeVoiceDeviceCheck.tsx'),'utf8');
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
 assert.match(component,/FileSystem\.deleteAsync\(path/);
 assert.match(component,/await recorder\.stop\(\)/);
 assert.doesNotMatch(component,/documentDirectory|SecureStore|AsyncStorage/);
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
