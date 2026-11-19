const {test}=require('node:test');
const assert=require('node:assert/strict');
const {evaluateVoiceDeviceCheck,isPrivateVoiceDeviceCheckUri,voiceDeviceSignalLevel,VOICE_DEVICE_CHECK_DURATION_MS,VOICE_DEVICE_CHECK_MIN_DURATION_MS,VOICE_DEVICE_CHECK_MIN_SIGNAL_DB}=require('../src/voiceDeviceCheck');

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

test('unverified temporary-file cleanup never reports a passed microphone check',()=>{
 assert.equal(evaluateVoiceDeviceCheck({permissionGranted:true,durationMs:6000,fileBytes:1024,peakMeteringDb:-5,cleanupVerified:false}),'cleanup_failed');
 assert.equal(evaluateVoiceDeviceCheck({permissionGranted:true,durationMs:6000,fileBytes:1024,peakMeteringDb:-5,cleanupVerified:true}),'passed');
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

test('missing native metering is reported as inconclusive, not passed',()=>{
 assert.equal(evaluateVoiceDeviceCheck({permissionGranted:true,durationMs:6000,fileBytes:1024,peakMeteringDb:null}),'metering_unavailable');
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
