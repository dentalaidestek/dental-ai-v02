export const VOICE_DEVICE_CHECK_DURATION_MS=6000;
export const VOICE_DEVICE_CHECK_MIN_DURATION_MS=5500;
export const VOICE_DEVICE_CHECK_MIN_SIGNAL_DB=-40;

const PRIVATE_DEVICE_CHECK_FILE=/^[A-Za-z0-9][A-Za-z0-9._-]{0,180}\.m4a$/i;

/** Accept only a direct .m4a child of Expo's app-private cache directory. */
export function isPrivateVoiceDeviceCheckUri(
 uri:unknown,cacheDirectory:string|null|undefined
):uri is string{
 if(typeof uri!=='string'||typeof cacheDirectory!=='string'||
    !cacheDirectory.startsWith('file:///')||!cacheDirectory.endsWith('/'))return false;
 if(!uri.startsWith(cacheDirectory))return false;
 return PRIVATE_DEVICE_CHECK_FILE.test(uri.slice(cacheDirectory.length));
}

export type VoiceDeviceCheckFileSystem={
 getInfoAsync(uri:string):Promise<{exists:boolean}>;
 deleteAsync(uri:string,options:{idempotent:true}):Promise<unknown>;
};

/** Delete only a validated cache file and confirm that it is absent afterward. */
export async function removePrivateVoiceDeviceCheckFile(
 uri:unknown,cacheDirectory:string|null|undefined,fileSystem:VoiceDeviceCheckFileSystem
):Promise<boolean>{
 if(!isPrivateVoiceDeviceCheckUri(uri,cacheDirectory))return false;
 try{
  const before=await fileSystem.getInfoAsync(uri);
  if(!before.exists)return true;
  await fileSystem.deleteAsync(uri,{idempotent:true});
  const after=await fileSystem.getInfoAsync(uri);
  return after.exists!==true;
 }catch{return false;}
}

export type VoiceDeviceCheckOutcome=
 | 'permission_denied'
 | 'capture_incomplete'
 | 'no_audio_file'
 | 'metering_unavailable'
 | 'low_signal'
 | 'cleanup_failed'
 | 'audio_mode_restore_failed'
 | 'passed';

export type VoiceDeviceCheckInput={
 permissionGranted:boolean;
 durationMs:number;
 fileBytes:number;
 peakMeteringDb:number|null;
 cleanupVerified?:boolean;
 audioModeRestored?:boolean;
};

/** Classifies only local capture metadata. It never accepts or returns audio or transcript data. */
export function evaluateVoiceDeviceCheck(input:VoiceDeviceCheckInput):VoiceDeviceCheckOutcome{
 if(input.cleanupVerified===false)return 'cleanup_failed';
 if(input.audioModeRestored===false)return 'audio_mode_restore_failed';
 if(!input.permissionGranted)return 'permission_denied';
 if(!Number.isFinite(input.durationMs)||input.durationMs<VOICE_DEVICE_CHECK_MIN_DURATION_MS)return 'capture_incomplete';
 if(!Number.isFinite(input.fileBytes)||input.fileBytes<=0)return 'no_audio_file';
 if(input.peakMeteringDb===null||!Number.isFinite(input.peakMeteringDb))return 'metering_unavailable';
 if(input.peakMeteringDb<VOICE_DEVICE_CHECK_MIN_SIGNAL_DB)return 'low_signal';
 return 'passed';
}

/** Expo Audio reports meter values in dBFS; map -60..0 dB to a bounded display level. */
export function voiceDeviceSignalLevel(meteringDb:number|null|undefined):number{
 if(typeof meteringDb!=='number'||!Number.isFinite(meteringDb))return 0;
 return Math.max(0,Math.min(1,(meteringDb+60)/60));
}
