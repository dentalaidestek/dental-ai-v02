export const VOICE_DEVICE_CHECK_DURATION_MS=6000;
export const VOICE_DEVICE_CHECK_MIN_DURATION_MS=5500;
export const VOICE_DEVICE_CHECK_MIN_SIGNAL_DB=-40;

export type VoiceDeviceCheckOutcome=
 | 'permission_denied'
 | 'capture_incomplete'
 | 'no_audio_file'
 | 'metering_unavailable'
 | 'low_signal'
 | 'passed';

export type VoiceDeviceCheckInput={
 permissionGranted:boolean;
 durationMs:number;
 fileBytes:number;
 peakMeteringDb:number|null;
};

/** Classifies only local capture metadata. It never accepts or returns audio or transcript data. */
export function evaluateVoiceDeviceCheck(input:VoiceDeviceCheckInput):VoiceDeviceCheckOutcome{
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
