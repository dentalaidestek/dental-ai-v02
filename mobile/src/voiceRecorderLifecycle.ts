/**
 * Distinguish an unexpected recorder stop from the normal stop/start gap
 * while rotating a bounded native audio segment.
 *
 * Expo Audio reports isRecording=false while a segment is being finalized.
 * The caller resets its previous-recording marker before invoking stop(),
 * then uses this guard for genuine stops outside an owned transition.
 */
export function isUnexpectedVoiceRecorderStop(
 wasRecording:boolean,
 recordingRequested:boolean,
 hasActiveSegment:boolean,
 transitionInProgress:boolean
):boolean{
 return wasRecording&&recordingRequested&&hasActiveSegment&&!transitionInProgress;
}

/**
 * Wait for Expo Audio's native recorder to confirm that capture really began.
 * Permission being granted and record() returning are not sufficient evidence.
 */
export async function waitForVoiceRecorderStarted(
 getStatus:()=>{isRecording?:boolean},
 wait:(milliseconds:number)=>Promise<void>=(milliseconds)=>new Promise(resolve=>setTimeout(resolve,milliseconds))
):Promise<boolean>{
 for(let attempt=0;attempt<10;attempt++){
  try{if(getStatus()?.isRecording===true)return true;}catch{}
  if(attempt<9)await wait(100);
 }
 return false;
}

/**
 * Restore the app-wide playback route after a native recording has stopped.
 * Expo Audio mode is global to the app, so every terminal/failed capture path
 * must attempt to leave recording mode. A false result is surfaced to the UI.
 */
export async function restoreVoiceAudioMode(restore:()=>Promise<unknown>):Promise<boolean>{
 try{
  await restore();
  return true;
 }catch{
  return false;
 }
}
