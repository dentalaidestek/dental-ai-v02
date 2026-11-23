import {API_BASE} from './api';

const API_ROOT=API_BASE.replace(/\/+$/,'');
let nextPatientAnalysisHistoryScope=0;

export type PatientAnalysisHistoryImageAssetId=number|null;

/** A short opaque identity for private history images; never derive it from a bearer token. */
export function createPatientAnalysisHistoryImageScope():string{
 nextPatientAnalysisHistoryScope++;
 return 'patient-analysis-history-scope-'+nextPatientAnalysisHistoryScope;
}

/** Force a new native image component for another authorized session, asset or retry. */
export function patientAnalysisHistoryImageKey(
 scope:string,
 analysisId:number,
 assetId:PatientAnalysisHistoryImageAssetId,
 revision=0,
):string{
 if(typeof scope!=='string'||!/^patient-analysis-history-scope-[1-9]\d*$/.test(scope)||
    !Number.isSafeInteger(analysisId)||analysisId<=0||
    (assetId!==null&&(!Number.isSafeInteger(assetId)||assetId<=0))||
    !Number.isSafeInteger(revision)||revision<0)
  throw Error('Hasta analiz görsel kapsamı doğrulanamadı.');
 return 'patient-analysis-history:'+scope+':'+analysisId+':'+(assetId===null?'legacy-radiograph':assetId)+':'+revision;
}

/** Private analysis images are revalidated by the authenticated API on every mount. */
export function patientAnalysisHistoryImageSource(
 token:string,
 analysisId:number,
 assetId:PatientAnalysisHistoryImageAssetId,
){
 if(typeof token!=='string'||!token.trim()||/\s/.test(token)||token.length>8192||
    !Number.isSafeInteger(analysisId)||analysisId<=0||
    (assetId!==null&&(!Number.isSafeInteger(assetId)||assetId<=0)))
  throw Error('Hasta analiz görsel oturumu veya kimliği doğrulanamadı.');
 const suffix=assetId===null?'legacy-radiograph':'assets/'+assetId;
 return {
  uri:API_ROOT+'/analyses/'+analysisId+'/'+suffix,
  headers:{Authorization:'Bearer '+token},
  cache:'reload' as const,
 };
}
