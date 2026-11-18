import type {MobileAnalysis} from './analysisApi';

const terminalAnalysisStatuses=new Set([
 'VISION_READY','VISION_ERROR','AI_ANALYZED','AI_FINAL',
 'ANALYSIS_COMPLETE','COMPLETED','FAILED','ERROR','CANCELLED',
]);
const terminalJobStatuses=new Set(['DONE','FAILED','CANCELLED']);

/** Only keep the analysis status fallback alive while a server job can still change. */
export function analysisNeedsPolling(snapshot:Pick<MobileAnalysis,'analysis'|'job'>|null|undefined):boolean{
 if(!snapshot?.analysis)return false;
 const status=String(snapshot.analysis.status||'').trim().toUpperCase();
 if(terminalAnalysisStatuses.has(status))return false;
 const jobStatus=String(snapshot.job?.status||'').trim().toUpperCase();
 if(terminalJobStatuses.has(jobStatus))return false;
 return true;
}

/** 15s → 30s → 60s, with bounded jitter to avoid synchronized client bursts. */
export function analysisPollDelay(attempt:number,random=Math.random()):number{
 const safeAttempt=Number.isSafeInteger(attempt)?Math.max(0,attempt):0;
 const base=Math.min(60000,15000*2**Math.min(safeAttempt,2));
 const spread=Math.min(5000,Math.round(base*.1));
 const sample=Number.isFinite(random)?Math.max(0,Math.min(1,random)):.5;
 return base-spread+Math.round(spread*2*sample);
}

export const MAX_ANALYSIS_POLL_ATTEMPTS=40;
