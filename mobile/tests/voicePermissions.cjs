const {test}=require('node:test');
const assert=require('node:assert/strict');
const config=require('../app.json').expo;

test('voice examination APK requests Android microphone permission',()=>{
 assert.equal(config.android.blockedPermissions.includes('android.permission.RECORD_AUDIO'),false);
 const plugin=config.plugins.find(item=>Array.isArray(item)&&item[0]==='expo-audio');
 assert.ok(plugin,'expo-audio config plugin must be configured');
 assert.equal(plugin[1].recordAudioAndroid,true);
 assert.equal(typeof plugin[1].microphonePermission,'string');
 assert.ok(plugin[1].microphonePermission.length>0);
});

test('clinical voice recording permission has a clear iOS usage explanation',()=>{
 const plugin=config.plugins.find(item=>Array.isArray(item)&&item[0]==='expo-audio');
 assert.notEqual(plugin[1].microphonePermission,false);
});
