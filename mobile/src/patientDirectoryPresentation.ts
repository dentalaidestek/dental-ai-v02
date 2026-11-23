export type PatientDirectoryFields = {
 anonymous_id?:string|null;
 phone?:string|null;
};

// The web directory filters on every input event. Native keeps the same
// behavior without sending one request per keystroke.
export const PATIENT_DIRECTORY_SEARCH_DEBOUNCE_MS=300;

// A bare phone number is typed with spaces, dots, dashes or parentheses
// ("0532 123 45 67"); the stored value is the bare 11-digit number, so the
// separators are stripped before the query reaches the server. Name search is
// untouched.
export function normalizePatientDirectorySearch(value:string):string{
 const normalized=value.trim().replace(/\s+/g," ");
 return /^\d[\d\s().-]{6,}$/.test(normalized)?normalized.replace(/\D/g,""):normalized;
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
