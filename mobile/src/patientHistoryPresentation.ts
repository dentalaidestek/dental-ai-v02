export type PatientAnalysisHistoryItem = {
 id:number;
 status:string;
 created_at:string;
 tooth_number?:string|null;
 is_voice_review?:boolean;
};

export type PatientHistoryStatusTone = "success"|"danger"|"warning";

export function patientAnalysisHistoryStatus(item:Pick<PatientAnalysisHistoryItem,"status"|"is_voice_review">):string {
 if(item.is_voice_review)return "Kaydedildi";
 if(["AI_ANALYZED","FINAL","ANALYSIS_COMPLETE"].includes(item.status))return "Başarılı";
 if(["AI_ERROR","FAILED","ERROR"].includes(item.status))return "Başarısız";
 return "Yarım kaldı";
}

export function patientAnalysisHistoryStatusTone(item:Pick<PatientAnalysisHistoryItem,"status"|"is_voice_review">):PatientHistoryStatusTone {
 if(item.is_voice_review||["AI_ANALYZED","FINAL","ANALYSIS_COMPLETE"].includes(item.status))return "success";
 if(["AI_ERROR","FAILED","ERROR"].includes(item.status))return "danger";
 return "warning";
}

export function patientAnalysisHistoryTitle(item:Pick<PatientAnalysisHistoryItem,"id"|"is_voice_review">):string {
 return `${item.is_voice_review?"Sesli muayene":"Analiz"} #${item.id}`;
}

export function patientAnalysisHistoryTooth(item:Pick<PatientAnalysisHistoryItem,"tooth_number"|"is_voice_review">):string|null {
 const tooth=typeof item.tooth_number==="string"?item.tooth_number.trim():"";
 return !item.is_voice_review&&tooth? `Diş ${tooth}`:null;
}

export function patientAnalysisHistoryDate(value:unknown):string {
 if(typeof value!=="string"||!value.trim())return "Tarih bilgisi yok";
 const parsed=new Date(value);
 if(!Number.isFinite(parsed.getTime()))return "Tarih bilgisi yok";
 return parsed.toLocaleString("tr-TR");
}
