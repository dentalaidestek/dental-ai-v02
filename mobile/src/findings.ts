export function displayFindings(result: any): Array<any> {
  if (!Array.isArray(result?.findings)) return [];
  return result.findings.flatMap((f: any) => {
    if (f?.confidence == null || f.confidence === "") return [];
    const raw = Number(f.confidence);
    if (!Number.isFinite(raw) || raw < 0 || raw > 100) return [];
    const confidence = raw > 1 ? raw / 100 : raw;
    return confidence >= 0.5 ? [{ ...f, confidence }] : [];
  });
}
