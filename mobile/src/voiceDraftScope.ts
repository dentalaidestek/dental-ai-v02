/**
 * In-memory scope fence for asynchronous native voice draft work.
 * The persistent draft key is already bound to both owner and patient.
 */
export function isVoiceDraftScopeCurrent(expectedKey:string,activeKey:string):boolean{
 return typeof expectedKey==='string'&&expectedKey.length>0&&expectedKey===activeKey;
}
