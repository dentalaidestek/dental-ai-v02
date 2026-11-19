export type PatientDirectoryFields = {
 anonymous_id?:string|null;
 phone?:string|null;
};

// The web directory filters on every input event. Native keeps the same
// behavior without sending one request per keystroke.
export const PATIENT_DIRECTORY_SEARCH_DEBOUNCE_MS=300;

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
