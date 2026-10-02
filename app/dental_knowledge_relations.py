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
)
