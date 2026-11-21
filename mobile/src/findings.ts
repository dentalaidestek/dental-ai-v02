export function displayFindings(result: any): Array<any> {
  if (!Array.isArray(result?.findings)) return [];
  return result.findings.flatMap((f: any) => {
    // The validated web clinical schema uses string[]; confidence belongs to
    // structured vision findings only. Never fabricate a probability for text.
    if (typeof f === "string") return f.trim() ? [{label:f.trim(),confidence:null,kind:"clinical_text"}] : [];
    if (f?.confidence == null || f.confidence === "") return [];
    const raw = Number(f.confidence);
    if (!Number.isFinite(raw) || raw < 0 || raw > 100) return [];
    const confidence = raw > 1 ? raw / 100 : raw;
    return confidence >= 0.5 ? [{ ...f, confidence }] : [];
  });
}
