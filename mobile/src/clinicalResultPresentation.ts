export type ClinicalResultSectionId =
  | 'most_likely'
  | 'findings'
  | 'treatment_options'
  | 'treatment_cautions'
  | 'preferred_approach'
  | 'differential'
  | 'recommended_evaluation'
  | 'uncertainty';

export type ClinicalResultSection = {
  id: ClinicalResultSectionId;
  label: string;
  kind: 'text' | 'unordered' | 'ordered';
  value: unknown;
};

export type ClinicalResultPresentationInput = {
  status?: string;
  most_likely?: unknown;
  findings?: unknown;
  treatment_options?: unknown;
  treatment_cautions?: unknown;
  preferred_approach?: unknown;
  differential?: unknown;
  recommended_evaluation?: unknown;
  uncertainty?: unknown;
};

export const CLINICAL_QUESTION_GUIDANCE =
  'Yalnız tedavi sırasını, uygulanabilirliği veya vaka-özel komplikasyon riskini değiştirebilecek eksik bilgiler sorulur.';

export function clinicalResultTitle(status: string): string {
  if (status === 'FINAL') return 'Nihai Klinik Değerlendirme';
  if (status === 'INITIAL' || status === 'ANALYSIS_COMPLETE') return 'Klinik Değerlendirme';
  if (status === 'NEEDS_INFO') return 'Kritik klinik bilgiler gerekiyor';
  if (status === 'READY') return 'Ön değerlendirme';
  if (status === 'AI_ANALYZING') return 'AI analizi sürüyor';
  return 'Sonuç durumu: ' + status;
}

/**
 * Keep the native clinical result in the same section order and scope as
 * app/templates/result.html. Vision-specific confidence and evidence remain
 * in the viewer; this list is the web result page's clinical summary.
 */
export function clinicalResultSections(
  result: ClinicalResultPresentationInput | null | undefined,
): ClinicalResultSection[] {
  if (!result) return [];
  const sections: ClinicalResultSection[] = [
    { id: 'most_likely', label: 'En Olası Durum', kind: 'text', value: result.most_likely },
    { id: 'findings', label: 'Önemli Bulgular', kind: 'unordered', value: result.findings },
    { id: 'treatment_options', label: 'Tedavi Seçenekleri', kind: 'ordered', value: result.treatment_options },
    { id: 'treatment_cautions', label: 'Tedaviye Bağlı Dikkat Edilecekler', kind: 'unordered', value: result.treatment_cautions },
    { id: 'preferred_approach', label: 'Önerilen Yaklaşım', kind: 'text', value: result.preferred_approach },
    { id: 'differential', label: 'Diğer Olası Tanılar', kind: 'unordered', value: result.differential },
  ];
  // Preliminary-only fields stay out of the signed-off FINAL view, matching
  // the web result page: uncertainty and recommended evaluation belong to the
  // clinician's working screen, not the durable record.
  if (result.status !== 'FINAL') {
    if (Array.isArray(result.recommended_evaluation) && result.recommended_evaluation.length) {
      sections.push({ id: 'recommended_evaluation', label: 'Önerilen Değerlendirme', kind: 'ordered', value: result.recommended_evaluation });
    }
    if (typeof result.uncertainty === 'string' && result.uncertainty) {
      sections.push({ id: 'uncertainty', label: 'Belirsizlik', kind: 'text', value: result.uncertainty });
    }
  }
  return sections;
}
