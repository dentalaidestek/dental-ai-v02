export type PatientDirectoryFields = {
 anonymous_id?:string|null;
 phone?:string|null;
};

export function normalizePatientDirectorySearch(value:string):string{
 return value.trim().replace(/\s+/g," ");
}

export function patientDirectoryDetails(patient:PatientDirectoryFields):string[]{
 return [
  `Hasta No: ${patient.anonymous_id?.trim()||"-"}`,
  `Telefon: ${patient.phone?.trim()||"-"}`,
 ];
}

export function patientDirectoryAgeLabel(age:number|null|undefined):string{
 return age==null?"Hasta kaydı":`${age} yaş`;
}
