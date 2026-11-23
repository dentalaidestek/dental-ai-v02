// Behavioral contracts for the native push bridge, exercised through the same
// CommonJS boundary as the app: notification response de-duplication, payload
// edge cases that must never navigate or crash, and dead-token cleanup that
// unregisters the stored device when the OS permission is gone.
const ts=require('typescript'),fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),{test}=require('node:test');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const DEVICE_UUID='5f0c9b8a-3e2d-4a1b-8c6d-9e0f1a2b3c4d';

function loadNativePush({permissions,store,modernApi,coldStart=null}){
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/nativePush.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 const targetCode=ts.transpileModule(fs.readFileSync(require.resolve('../src/notificationTarget.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 const targetExports={};vm.runInNewContext(targetCode,{exports:targetExports});
 const pushTokenExports={isValidExpoPushToken:value=>typeof value==='string'&&/^(?:Expo|Exponent)PushToken\[[A-Za-z0-9_-]{8,128}\]$/.test(value)};
 const secureStore={
  getItemAsync:key=>Promise.resolve(store[key]??null),
  setItemAsync:async(key,value)=>{store[key]=value},
  deleteItemAsync:async key=>{delete store[key]},
 };
 const notifications={
  AndroidImportance:{DEFAULT:3},
  setNotificationHandler(){},
  setNotificationChannelAsync:async()=>{},
  getPermissionsAsync:async()=>permissions,
  requestPermissionsAsync:async()=>permissions,
  getExpoPushTokenAsync:async()=>({data:'ExpoPushToken[bridgetesttoken]'}),
  addNotificationResponseReceivedListener:handler=>{notifications.listeners.push(handler);return{remove(){}}},
  getLastNotificationResponseAsync:async()=>coldStart,
 };
 notifications.listeners=[];
 const exports={};
 vm.runInNewContext(code,{exports,setTimeout,clearTimeout,
  require:name=>name==='react-native'?{Platform:{OS:'android'}}
   :name==='expo-secure-store'?secureStore
   :name==='expo-crypto'?{randomUUID:()=>DEVICE_UUID,getRandomBytesAsync:async length=>new Uint8Array(length).fill(7)}
   :name==='expo-constants'?{default:{}}
   :name==='expo-notifications'?notifications
   :name==='./modernApi'?modernApi
   :name==='./pushToken'?pushTokenExports
   :name==='./notificationTarget'?targetExports
   :(()=>{throw new Error('unexpected require '+name)})()});
 return {push:exports,notifications,store};
}

test('duplicate tap identifiers navigate once while distinct taps navigate each time',async()=>{
 const responses=[];
 const {push,notifications}=loadNativePush({permissions:{granted:true,canAskAgain:true,status:'granted'},store:{},
  // The cold-start read delivers the same tap the listener just handled.
  coldStart:{notification:{request:{identifier:'tap-1',content:{data:{kind:'consultation',case_id:12}}}}}});
 const stop=push.subscribeToNativePushResponses(target=>responses.push(target));
 notifications.listeners[0]({notification:{request:{identifier:'tap-1',content:{data:{kind:'consultation',case_id:12}}}}});
 await tick();
 // A later, deliberate tap with a fresh identifier must navigate again.
 notifications.listeners[0]({notification:{request:{identifier:'tap-2',content:{data:{kind:'consultation',case_id:12}}}}});
 await tick();
 assert.deepEqual(responses.map(target=>target.route.params.id),[12,12]);
 stop();
});

test('missing, extra and non-object Expo payloads never navigate or crash',async()=>{
 const responses=[];
 const {push,notifications}=loadNativePush({permissions:{granted:true,canAskAgain:true,status:'granted'},store:{}});
 const stop=push.subscribeToNativePushResponses(target=>responses.push(target));
 for(const data of [undefined,'kind','{}',{},null,{kind:'consultation'},{kind:'consultation',case_id:0},{kind:'notification'},{kind:'unknown',case_id:9},{kind:'consultation',case_id:'not-a-number'},{kind:'consultation',case_id:'9007199254740992',anything:'extra'}]){
  notifications.listeners[0]({notification:{request:{identifier:'edge-'+String(responses.length)+typeof data,content:{data}}}});
 }
 await tick();
 assert.equal(responses.length,0);
 // Extra unknown fields beside a valid id still navigate to the allowlisted screen.
 notifications.listeners[0]({notification:{request:{identifier:'extra-ok',content:{data:{kind:'notification',notice_id:77,extra:{deep:true}}}}}});
 await tick();
 assert.equal(responses.length,1);
 assert.equal(responses[0].route.screen,'Notifications');
 assert.equal(responses[0].route.params.noticeId,77);
 stop();
});

test('a lost OS permission unregisters the stored device and clears the account opt-in',async()=>{
 const store={'dai.push.device_id':DEVICE_UUID,'dai.push.enabled.5':'1','dai.push.delivery.5':'1'};
 const unregistered=[];
 const {push}=loadNativePush({permissions:{granted:false,canAskAgain:false,status:'denied'},store,
  modernApi:{unregisterPushDevice:async(token,deviceId)=>{unregistered.push({token,deviceId});return {ok:true}},registerPushDevice:async()=>{throw new Error('must not register')},claimPushDevice:async()=>{throw new Error('must not claim')}}});
 const refreshed=await push.refreshNativePushRegistration('tok',5);
 assert.equal(refreshed,false);
 assert.deepEqual(unregistered,[{token:'tok',deviceId:DEVICE_UUID}]);
 assert.equal(store['dai.push.enabled.5'],undefined);
 assert.equal(store['dai.push.delivery.5'],undefined);
});
