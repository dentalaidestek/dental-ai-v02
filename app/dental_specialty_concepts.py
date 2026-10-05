"""Specialty vocabulary packs for the dental retrieval ontology.

These are retrieval concepts, not clinical answer facts.
"""
SPECIALTY_CONCEPTS = {
    "orthodontics": (
        ("cephalometry", "sefalometri", ("cephalometry", "sefalometrik analiz"), "procedure"),
        ("skeletal_class_ii", "iskeletsel Sınıf II", ("skeletal class II", "iskeletsel class II"), "classification"),
        ("skeletal_class_iii", "iskeletsel Sınıf III", ("skeletal class III", "iskeletsel class III"), "classification"),
        ("overjet", "overjet", ("horizontal overbite",), "measurement"),
        ("overbite", "overbite", ("vertical overbite",), "measurement"),
        ("open_bite", "açık kapanış", ("open bite",), "finding"),
        ("crossbite", "çapraz kapanış", ("crossbite",), "finding"),
    ),
    "endodontics": (
        ("root_canal_treatment", "kanal tedavisi", ("root canal treatment", "endodontik tedavi"), "procedure"),
        ("reversible_pulpitis", "reversible pulpitis", ("geri dönüşümlü pulpitis",), "diagnosis"),
        ("irreversible_pulpitis", "irreversible pulpitis", ("geri dönüşümsüz pulpitis",), "diagnosis"),
        ("periapical_lesion", "periapikal lezyon", ("periapical lesion", "apikal lezyon"), "finding"),
        ("root_resorption", "kök rezorpsiyonu", ("root resorption", "kök rezorbsiyonu"), "finding"),
    ),
    "periodontology": (
        ("periodontitis", "periodontitis", ("periodontitis",), "diagnosis"),
        ("gingivitis", "gingivitis", ("gingivitis", "diş eti iltihabı"), "diagnosis"),
        ("furcation", "furkasyon", ("furcation", "furkasyon tutulumu"), "finding"),
        ("calculus", "diş taşı", ("dental calculus", "kalkulus"), "finding"),
        ("plaque", "dental plak", ("dental plaque", "bakteriyel plak"), "finding"),
    ),
    "oral_surgery": (
        ("extraction", "diş çekimi", ("tooth extraction", "ekstraksiyon"), "procedure"),
        ("dry_socket", "alveolit", ("dry socket", "alveolar osteitis"), "complication"),
        ("oroantral_communication", "oroantral açıklık", ("oroantral communication", "OAC"), "complication"),
    ),
    "radiology": (
        ("radiolucency", "radyolüsensi", ("radiolucent", "radyolüsent"), "finding"),
        ("radiopacity", "radyoopasite", ("radiopaque", "radyoopak"), "finding"),
        ("lamina_dura", "lamina dura", ("lamina dura",), "anatomy"),
        ("pdl_space", "periodontal ligament aralığı", ("PDL space", "periodontal ligament space"), "anatomy"),
    ),
    "prosthodontics": (
        ("impression", "ölçü", ("impression", "dental impression"), "procedure"),
        ("alginate", "aljinat", ("alginate", "irreversible hydrocolloid"), "material"),
        ("pvs", "A silikon", ("PVS", "polyvinyl siloxane", "addition silicone"), "material"),
        ("gic", "cam iyonomer siman", ("glass ionomer cement", "GIC"), "material"),
    ),
    "restorative": (
        ("smear_layer", "smear tabakası", ("smear layer",), "finding"),
        ("acid_etch", "asit pürüzlendirme", ("acid etching", "etching"), "procedure"),
        ("composite", "kompozit rezin", ("composite resin", "kompozit"), "material"),
        ("adhesive", "dental adeziv", ("dental adhesive", "bonding agent"), "material"),
    ),
    "pediatric_dentistry": (
        ("pulpotomy", "pulpotomi", ("pulpotomy",), "procedure"),
        ("pulpectomy", "pulpektomi", ("pulpectomy",), "procedure"),
        ("space_maintainer", "yer tutucu", ("space maintainer",), "appliance"),
    ),
    "oral_pathology": (
        ("cyst", "kist", ("odontogenic cyst", "cyst"), "diagnosis"),
        ("odontogenic_tumor", "odontojenik tümör", ("odontogenic tumor",), "diagnosis"),
        ("leukoplakia", "lökoplaki", ("leukoplakia",), "diagnosis"),
    ),
    "tmd": (
        ("disc_displacement", "disk deplasmanı", ("disc displacement", "disk displacement"), "diagnosis"),
        ("crepitation", "krepitasyon", ("crepitus", "crepitation"), "finding"),
        ("clicking", "klik sesi", ("clicking", "click"), "finding"),
    ),
}
