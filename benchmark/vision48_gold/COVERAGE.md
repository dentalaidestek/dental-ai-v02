# Vision48 Gold Coverage v1

- Exact independent gold candidate: **14/48**
- Partial/secondary independent reference only: **9/48**
- Independent gold gap: **25/48**

> `exact` burada “etiket semantiği Vision48 koduyla doğrudan eşleşebiliyor” demektir; veri erişimi, lisans ve negatif-anotasyon bütünlüğü ayrıca doğrulanır. `partial` ise güçlü ama canonical kodla birebir aynı endpoint olmayan referanstır.

## Exact

- `MISSING_TOOTH` — mopg7_v4
- `SUPERNUMERARY_TOOTH` — dual_labeled_500
- `IMPACTED_TOOTH` — inredd_pan924
- `IMPACTED_THIRD_MOLAR` — inredd_pan924
- `RESIDUAL_ROOT` — inredd_pan924, dual_labeled_500
- `FILLING` — dual_labeled_500
- `CROWN` — inredd_pan924, mopg7_v4, dual_labeled_500
- `PONTIC` — inredd_pan924
- `IMPLANT` — inredd_pan924
- `ROOT_CANAL_TREATED` — inredd_pan924, mopg7_v4, dual_labeled_500
- `ENDO_POST` — inredd_pan924
- `CARIES` — inredd_pan924, mopg7_v4, dual_labeled_500
- `PERIAPICAL_RADIOLUCENCY` — hanoi_periapical
- `FURCATION_BONE_LOSS` — pdcnn_perio1747

## Partial / secondary only

- `UNERUPTED_TOOTH` — inredd_pan924, dentalopg1550
- `BRIDGE` — dentalopg1550
- `JAW_RADIOLUCENT_LESION` — toothpix_8655, tufts1000
- `JAW_RADIOPAQUE_LESION` — toothpix_8655, tufts1000
- `MIXED_DENSITY_JAW_LESION` — toothpix_8655, tufts1000
- `HORIZONTAL_BONE_LOSS` — boneloss_pan769
- `VERTICAL_BONE_LOSS` — boneloss_pan769
- `PERI_IMPLANT_BONE_LOSS` — boneloss_pan769
- `MANDIBULAR_CANAL_PROXIMITY` — contact_m3m_iac

## Gap / UNMEASURED

- `RETAINED_PRIMARY_TOOTH`
- `INLAY_ONLAY`
- `IMPLANT_SUPPORTED_CROWN`
- `UNDERFILLED_ROOT_CANAL`
- `OVERFILLED_ROOT_CANAL`
- `BROKEN_ENDO_INSTRUMENT`
- `APICAL_SURGERY`
- `DEEP_CARIES`
- `RECURRENT_CARIES`
- `PERIAPICAL_RADIOPACITY`
- `WIDENED_PDL`
- `LOSS_OF_LAMINA_DURA`
- `CONDENSING_OSTEITIS_PATTERN`
- `EXTERNAL_ROOT_RESORPTION`
- `INTERNAL_ROOT_RESORPTION`
- `ROOT_DILACERATION`
- `TOOTH_FRACTURE`
- `ROOT_FRACTURE`
- `CALCULUS`
- `MAXILLARY_SINUS_MUCOSAL_THICKENING`
- `MAXILLARY_SINUS_OPACIFICATION`
- `CONDYLAR_FLATTENING`
- `CONDYLAR_EROSION`
- `CONDYLAR_ASYMMETRY`
- `ORTHODONTIC_APPLIANCE`

`UNMEASURED` kötü veya iyi anlamına gelmez; bağımsız uzman ground-truth henüz benchmark kataloğuna kilitlenmemiş demektir. `GAP_CANDIDATES.md` dosyasında erişim talebiyle alınabilecek veya semantik doğrulaması bekleyen adaylar ayrı tutulur.