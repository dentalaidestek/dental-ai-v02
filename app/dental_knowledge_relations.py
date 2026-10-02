"""High-confidence dental retrieval relations.

These edges only expand retrieval candidates. They are not clinical facts
presented to users; final answers remain grounded in uploaded materials.
"""
from app.dental_knowledge_graph import DentalEdge, Relation

DENTAL_RELATION_EDGES = (
    # Endodontics: diagnosis -> procedure/material/assessment
    DentalEdge("reversible_pulpitis", Relation.HAS_TREATMENT, "root_canal_treatment", 0.72),
    DentalEdge("irreversible_pulpitis", Relation.HAS_TREATMENT, "root_canal_treatment", 0.92),
    DentalEdge("pulp_necrosis", Relation.HAS_TREATMENT, "root_canal_treatment", 0.90),
    DentalEdge("root_canal_treatment", Relation.HAS_MATERIAL, "gutta_percha", 0.90),
    DentalEdge("root_canal_treatment", Relation.HAS_MATERIAL, "sodium_hypochlorite", 0.86),
    DentalEdge("root_canal_treatment", Relation.HAS_MATERIAL, "edta", 0.82),
    DentalEdge("working_length", Relation.ASSESSED_BY, "apical_constriction", 0.88),
    DentalEdge("regenerative_endodontics", Relation.ASSOCIATED_WITH, "apexogenesis", 0.72),

    # Periodontology: findings/indices -> assessment/procedure/classification
    DentalEdge("periodontitis", Relation.ASSESSED_BY, "probing_depth", 0.92),
    DentalEdge("periodontitis", Relation.ASSESSED_BY, "attachment_loss", 0.94),
    DentalEdge("periodontitis", Relation.HAS_CLINICAL_FEATURE, "bop", 0.82),
    DentalEdge("periodontitis", Relation.HAS_RADIOGRAPHIC_FEATURE, "bone_loss", 0.90),
    DentalEdge("periodontitis", Relation.HAS_STAGE, "perio_stage", 0.96),
    DentalEdge("periodontitis", Relation.HAS_GRADE, "perio_grade", 0.96),
    DentalEdge("periodontitis", Relation.HAS_PROCEDURE, "root_planing", 0.86),
    DentalEdge("periodontitis", Relation.ASSESSED_BY, "cpi", 0.76),
    DentalEdge("gingivitis", Relation.ASSESSED_BY, "gingival_index", 0.84),
    DentalEdge("plaque", Relation.ASSESSED_BY, "plaque_index", 0.90),

    # Surgery / radiology: anatomy, risk and imaging
    DentalEdge("third_molar", Relation.ASSOCIATED_WITH, "dry_socket", 0.72),
    DentalEdge("extraction", Relation.HAS_COMPLICATION, "dry_socket", 0.94),
    DentalEdge("extraction", Relation.HAS_COMPLICATION, "oroantral_communication", 0.84),
    DentalEdge("extraction", Relation.HAS_COMPLICATION, "trismus", 0.78),
    DentalEdge("third_molar", Relation.ASSESSED_BY, "panoramic", 0.84),
    DentalEdge("ian", Relation.ASSESSED_BY, "cbct", 0.80),
    DentalEdge("ian_injury", Relation.ANATOMICAL_RELATION, "ian", 0.96),
    DentalEdge("mronj", Relation.HAS_RISK_FACTOR, "bisphosphonate", 0.94),
    DentalEdge("mronj", Relation.HAS_RISK_FACTOR, "antiresorptive", 0.94),
    DentalEdge("periapical_lesion", Relation.ASSESSED_BY, "periapical_radiograph", 0.90),
    DentalEdge("periapical_lesion", Relation.ASSESSED_BY, "periapical_index", 0.86),

    # Cariology / pediatric / restorative
    DentalEdge("caries", Relation.ASSESSED_BY, "icdas", 0.94),
    DentalEdge("caries", Relation.ASSESSED_BY, "dmft", 0.88),
    DentalEdge("caries", Relation.ASSESSED_BY, "dmfs", 0.86),
    DentalEdge("ecc", Relation.ASSOCIATED_WITH, "primary_tooth", 0.88),
    DentalEdge("mih", Relation.ASSOCIATED_WITH, "enamel", 0.80),
    DentalEdge("acid_etch", Relation.USED_FOR, "adhesive", 0.78),
    DentalEdge("composite", Relation.ASSOCIATED_WITH, "polymerization", 0.84),
    DentalEdge("composite", Relation.ASSOCIATED_WITH, "c_factor", 0.80),
    DentalEdge("composite", Relation.ASSOCIATED_WITH, "microleakage", 0.76),

    # Prosthodontics/materials
    DentalEdge("rpd", Relation.CLASSIFIED_BY, "kennedy_classification", 0.96),
    DentalEdge("impression", Relation.HAS_MATERIAL, "alginate", 0.84),
    DentalEdge("impression", Relation.HAS_MATERIAL, "pvs", 0.88),
    DentalEdge("impression", Relation.HAS_MATERIAL, "polyether", 0.84),
    DentalEdge("complete_denture", Relation.ASSOCIATED_WITH, "vdo", 0.80),
    DentalEdge("complete_denture", Relation.ASSOCIATED_WITH, "centric_relation", 0.82),

    # Local anesthesia / pharmacology
    DentalEdge("ianb", Relation.ANATOMICAL_RELATION, "ian", 0.96),
    DentalEdge("ianb", Relation.HAS_MATERIAL, "lidocaine", 0.72),
    DentalEdge("ianb", Relation.HAS_MATERIAL, "articaine", 0.72),
    DentalEdge("ianb", Relation.HAS_COMPLICATION, "anesthetic_paresthesia", 0.82),
    DentalEdge("local_anesthetic_paresthesia", Relation.ASSOCIATED_WITH, "ian", 0.76),

    # Oral pathology / imaging
    DentalEdge("odontogenic_keratocyst", Relation.HAS_RADIOGRAPHIC_FEATURE, "radiolucency", 0.82),
    DentalEdge("ameloblastoma_ext", Relation.HAS_RADIOGRAPHIC_FEATURE, "radiolucency", 0.78),

    # Developmental anatomy
    DentalEdge("odontogenesis", Relation.HAS_STAGE, "enamel_organ", 0.78),
    DentalEdge("amelogenesis", Relation.ASSOCIATED_WITH, "ameloblast", 0.96),
    DentalEdge("dentinogenesis", Relation.ASSOCIATED_WITH, "odontoblast", 0.96),
    DentalEdge("hertwig_root_sheath", Relation.USED_FOR, "odontogenesis", 0.76),
    # Orthodontic measurements/findings
    DentalEdge("cephalometry", Relation.ASSESSED_BY, "sna", 0.90),
    DentalEdge("cephalometry", Relation.ASSESSED_BY, "snb", 0.90),
    DentalEdge("cephalometry", Relation.ASSESSED_BY, "anb", 0.90),
    DentalEdge("skeletal_class_ii", Relation.ASSOCIATED_WITH, "skeletal_relation", 0.90),
    DentalEdge("skeletal_class_iii", Relation.ASSOCIATED_WITH, "skeletal_relation", 0.90),
    DentalEdge("overjet", Relation.ASSOCIATED_WITH, "malocclusion", 0.84),
    DentalEdge("overbite", Relation.ASSOCIATED_WITH, "malocclusion", 0.84),
    DentalEdge("open_bite", Relation.ASSOCIATED_WITH, "malocclusion", 0.86),
    DentalEdge("crossbite", Relation.ASSOCIATED_WITH, "malocclusion", 0.86),

    # Endodontic procedures/materials/findings
    DentalEdge("pulpitis", Relation.ASSOCIATED_WITH, "reversible_pulpitis", 0.88),
    DentalEdge("pulpitis", Relation.ASSOCIATED_WITH, "irreversible_pulpitis", 0.88),
    DentalEdge("pulpotomy", Relation.HAS_MATERIAL, "mta_material", 0.82),
    DentalEdge("pulpectomy", Relation.ASSOCIATED_WITH, "root_canal_treatment", 0.84),
    DentalEdge("apexification", Relation.HAS_MATERIAL, "mta_material", 0.86),
    DentalEdge("smear_layer", Relation.ASSOCIATED_WITH, "edta", 0.86),
    DentalEdge("root_resorption", Relation.ASSESSED_BY, "periapical_radiograph", 0.82),

    # Periodontal findings/procedures
    DentalEdge("furcation", Relation.ASSOCIATED_WITH, "furcation_classification", 0.94),
    DentalEdge("calculus", Relation.ASSOCIATED_WITH, "periodontitis", 0.80),
    DentalEdge("gingival_recession", Relation.ASSOCIATED_WITH, "periodontitis", 0.76),
    DentalEdge("gtr", Relation.ASSOCIATED_WITH, "periodontitis", 0.82),
    DentalEdge("gbr", Relation.ASSOCIATED_WITH, "alveolar_bone", 0.82),

    # Radiographic descriptors
    DentalEdge("radiolucent", Relation.ASSOCIATED_WITH, "radiolucency", 0.96),
    DentalEdge("radiopaque", Relation.ASSOCIATED_WITH, "radiopacity", 0.96),
    DentalEdge("lamina_dura", Relation.ANATOMICAL_RELATION, "pdl_space", 0.90),
    DentalEdge("bitewing", Relation.USED_FOR, "caries", 0.86),
    DentalEdge("cortication", Relation.HAS_RADIOGRAPHIC_FEATURE, "radiopaque", 0.76),
    DentalEdge("trabeculation", Relation.ANATOMICAL_RELATION, "alveolar_bone", 0.84),

    # Oral pathology
    DentalEdge("cyst", Relation.ASSOCIATED_WITH, "odontogenic_keratocyst", 0.76),
    DentalEdge("odontogenic_tumor", Relation.ASSOCIATED_WITH, "ameloblastoma_ext", 0.82),
    DentalEdge("leukoplakia", Relation.DIFFERENTIAL_WITH, "oscc", 0.78),
    DentalEdge("mucocele", Relation.ASSOCIATED_WITH, "oral_mucosa", 0.76),

    # TMD
    DentalEdge("disc_displacement", Relation.ANATOMICAL_RELATION, "articular_disc", 0.94),
    DentalEdge("clicking", Relation.ASSOCIATED_WITH, "disc_displacement", 0.88),
    DentalEdge("crepitation", Relation.ASSOCIATED_WITH, "tmj", 0.82),
    DentalEdge("crepitus", Relation.ASSOCIATED_WITH, "tmj", 0.82),

    # Prosthodontic/restorative materials
    DentalEdge("fpd", Relation.HAS_MATERIAL, "ceramic", 0.78),
    DentalEdge("rmgic", Relation.ASSOCIATED_WITH, "gic", 0.92),
    DentalEdge("resin_composite", Relation.ASSOCIATED_WITH, "composite", 0.96),
    DentalEdge("calcium_hydroxide", Relation.ASSOCIATED_WITH, "dental_pulp", 0.78),
    DentalEdge("biodentine", Relation.ASSOCIATED_WITH, "dental_pulp", 0.80),
    DentalEdge("zirconia", Relation.ASSOCIATED_WITH, "ceramic", 0.88),
    DentalEdge("lithium_disilicate", Relation.ASSOCIATED_WITH, "ceramic", 0.88),
    DentalEdge("pmma", Relation.ASSOCIATED_WITH, "complete_denture", 0.82),
    DentalEdge("zinc_oxide_eugenol", Relation.ASSOCIATED_WITH, "impression", 0.74),

    # Pediatric dentistry / indices
    DentalEdge("ssc", Relation.ASSOCIATED_WITH, "primary_tooth", 0.88),
    DentalEdge("mixed_dentition", Relation.ASSOCIATED_WITH, "primary_tooth", 0.82),
    DentalEdge("deft", Relation.ASSESSED_BY, "caries", 0.88),
    DentalEdge("psr", Relation.ASSESSED_BY, "periodontitis", 0.86),
    DentalEdge("papilla_bleeding_index", Relation.ASSESSED_BY, "gingivitis", 0.84),
    DentalEdge("mobility_grade", Relation.ASSOCIATED_WITH, "periodontitis", 0.78),
    DentalEdge("black_classification", Relation.CLASSIFIED_BY, "caries", 0.76),

    # Anatomy/histology/development
    DentalEdge("dental_pulp", Relation.PART_OF, "tooth", 0.96),
    DentalEdge("periodontal_ligament", Relation.ANATOMICAL_RELATION, "cementum", 0.92),
    DentalEdge("junctional_epithelium", Relation.ASSOCIATED_WITH, "gingiva", 0.92),
    DentalEdge("dental_lamina", Relation.ASSOCIATED_WITH, "odontogenesis", 0.94),
    DentalEdge("cementoblast", Relation.ASSOCIATED_WITH, "cementum", 0.94),

    # Anesthesia/pharmacology: conservative retrieval-only associations
    DentalEdge("mepivacaine", Relation.ASSOCIATED_WITH, "local_anesthesia", 0.88),
    DentalEdge("prilocaine", Relation.ASSOCIATED_WITH, "local_anesthesia", 0.88),
    DentalEdge("epinephrine", Relation.ASSOCIATED_WITH, "local_anesthesia", 0.84),
    DentalEdge("infiltration_anesthesia", Relation.ASSOCIATED_WITH, "local_anesthesia", 0.92),
    DentalEdge("intraligamentary_anesthesia", Relation.ASSOCIATED_WITH, "local_anesthesia", 0.92),
    DentalEdge("intrapulpal_anesthesia", Relation.ASSOCIATED_WITH, "local_anesthesia", 0.92),
    # Cross-validated terminology/procedure families (MeSH/ADA/AAO/AAPD).
    DentalEdge("endodontics", Relation.HAS_PROCEDURE, "pulpotomy", 0.96),
    DentalEdge("endodontics", Relation.HAS_PROCEDURE, "pulpectomy", 0.96),
    DentalEdge("endodontics", Relation.HAS_PROCEDURE, "apexification", 0.96),
    DentalEdge("endodontics", Relation.HAS_PROCEDURE, "regenerative_endodontics", 0.96),
    DentalEdge("root_canal_treatment", Relation.HAS_PROCEDURE, "root_canal_preparation", 0.94),
    DentalEdge("root_canal_treatment", Relation.HAS_PROCEDURE, "root_canal_obturation", 0.94),
    DentalEdge("root_canal_obturation", Relation.HAS_MATERIAL, "gutta_percha", 0.96),

    DentalEdge("malocclusion", Relation.CLASSIFIED_BY, "skeletal_class_ii", 0.86),
    DentalEdge("malocclusion", Relation.CLASSIFIED_BY, "skeletal_class_iii", 0.86),
    DentalEdge("malocclusion", Relation.HAS_CLINICAL_FEATURE, "overjet", 0.88),
    DentalEdge("malocclusion", Relation.HAS_CLINICAL_FEATURE, "overbite", 0.88),
    DentalEdge("malocclusion", Relation.HAS_CLINICAL_FEATURE, "open_bite", 0.90),
    DentalEdge("malocclusion", Relation.HAS_CLINICAL_FEATURE, "crossbite", 0.90),

    DentalEdge("dental_material", Relation.ASSOCIATED_WITH, "amalgam", 0.88),
    DentalEdge("dental_material", Relation.ASSOCIATED_WITH, "resin_composite", 0.92),
    DentalEdge("dental_material", Relation.ASSOCIATED_WITH, "gic", 0.92),
    DentalEdge("dental_material", Relation.ASSOCIATED_WITH, "rmgic", 0.90),
    DentalEdge("dental_material", Relation.ASSOCIATED_WITH, "zinc_oxide_eugenol", 0.88),
    DentalEdge("dental_material", Relation.ASSOCIATED_WITH, "resin_cement", 0.88),

    # Pediatric pulp therapy context. Keep these associations contextual rather
    # than universal treatment rules; final clinical claims still require notes.
    DentalEdge("primary_tooth", Relation.ASSOCIATED_WITH, "pulpotomy", 0.90),
    DentalEdge("primary_tooth", Relation.ASSOCIATED_WITH, "pulpectomy", 0.90),
    DentalEdge("immature_permanent_tooth", Relation.ASSOCIATED_WITH, "apexification", 0.92),
    DentalEdge("immature_permanent_tooth", Relation.ASSOCIATED_WITH, "regenerative_endodontics", 0.92),
    # Oral medicine/pathology: AAOM-supported retrieval relations.
    DentalEdge("leukoplakia", Relation.CLASSIFIED_BY, "oral_potentially_malignant_disorder", 0.92),
    DentalEdge("oral_erythroplakia", Relation.CLASSIFIED_BY, "oral_potentially_malignant_disorder", 0.92),
    DentalEdge("leukoplakia", Relation.ASSESSED_BY, "clinicopathologic_correlation", 0.94),
    DentalEdge("leukoplakia", Relation.ASSOCIATED_WITH, "oscc", 0.88),

    # Endodontic imaging: AAE/AAOMR selective-CBCT situations.
    DentalEdge("vertical_root_fracture", Relation.ASSESSED_BY, "cbct", 0.90),
    DentalEdge("external_cervical_resorption", Relation.ASSESSED_BY, "cbct", 0.92),
    DentalEdge("root_resorption", Relation.ASSESSED_BY, "cbct", 0.88),
    DentalEdge("perforation", Relation.ASSESSED_BY, "cbct", 0.86),
    DentalEdge("separated_instrument", Relation.ASSESSED_BY, "cbct", 0.84),
    DentalEdge("endodontic_failure", Relation.ASSESSED_BY, "cbct", 0.90),

    # Oral surgery complications.
    DentalEdge("extraction", Relation.HAS_COMPLICATION, "dry_socket", 0.96),
    DentalEdge("oroantral_communication", Relation.LEADS_TO, "oroantral_fistula", 0.82),

    # Pharmacology/antibiotic stewardship. Avoid universal drug=treatment edges.
    DentalEdge("antibiotic_stewardship", Relation.ASSOCIATED_WITH, "amoxicillin", 0.72),
    DentalEdge("antibiotic_stewardship", Relation.ASSOCIATED_WITH, "amoxicillin_clavulanate", 0.70),
    DentalEdge("antibiotic_stewardship", Relation.ASSOCIATED_WITH, "metronidazole", 0.70),
    DentalEdge("antibiotic_stewardship", Relation.ASSOCIATED_WITH, "clindamycin", 0.66),
    DentalEdge("systemic_involvement", Relation.ASSOCIATED_WITH, "antibiotic_stewardship", 0.88),
)
