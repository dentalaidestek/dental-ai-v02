import type {VoiceHistoryField} from './voiceApi';

export type PatientVoiceHistoryRow={key:string;label:string;value:string;analysisId:number};

const FIELD_ORDER:[string,string][]=[
 ['medical_history','Sistemik hastalıklar / sağlık geçmişi'],
 ['medications','İlaç beyanları'],
 ['allergies','Alerji beyanları'],
 ['family_history','Aile sağlık öyküsü'],
 ['dental_history','Önceki diş tedavileri'],
 ['oral_habits','Ağız bakımı ve alışkanlıklar'],
 ['materials','Konuşulan materyaller'],
];

export function patientVoiceHistoryRows(fields:Record<string,VoiceHistoryField>|null|undefined):PatientVoiceHistoryRow[]{
 if(!fields||typeof fields!=='object'||Array.isArray(fields))return [];
 return FIELD_ORDER.flatMap(([key,label])=>{
  const item=fields[key];
  if(!item||typeof item.value!=='string'||!item.value.trim()||!Number.isSafeInteger(item.analysis_id)||item.analysis_id<=0)return [];
  return [{key,label,value:item.value,analysisId:item.analysis_id}];
 });
}
