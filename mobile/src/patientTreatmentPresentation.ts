export type PatientTreatmentEditGate={
 busy:boolean;
 profileUncertain:boolean;
 treatmentUncertain:boolean;
 treatmentIntentReady:boolean;
 treatmentIntentBlocked:boolean;
 hasPendingTreatment:boolean;
 patientMutationBlocked:boolean;
};

/** Do not expose another treatment edit while a durable clinical mutation is unresolved. */
export function patientTreatmentCanEdit(gate:PatientTreatmentEditGate):boolean{
 return !gate.busy&&!gate.profileUncertain&&!gate.treatmentUncertain&&
  gate.treatmentIntentReady&&!gate.treatmentIntentBlocked&&
  !gate.hasPendingTreatment&&!gate.patientMutationBlocked;
}

export function patientTreatmentToothLabel(value:unknown):string{
 if(typeof value!=="string")return "Diş -";
 const tooth=value.trim();
 return /^(?:[1-4][1-8]|[5-8][1-5])$/.test(tooth)?"Diş "+tooth:"Diş -";
}

export function patientTreatmentDateLabel(value:unknown):string{
 return typeof value==="string"&&value.trim()?value.trim():"-";
}

export function patientTreatmentMaterialLabel(value:unknown):string|null{
 if(typeof value!=="string")return null;
 const material=value.trim();
 return material?material:null;
}
