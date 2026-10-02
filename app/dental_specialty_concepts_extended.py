"""Extended dental retrieval vocabulary.

Static data only: no model/provider calls and no clinical answer facts.
"""
EXTENDED_SPECIALTY_CONCEPTS = {
    "endodontics": (
        ("apexification", "apeksifikasyon", ("apexification",), "procedure"),
        ("apexogenesis", "apeksogenez", ("apexogenesis",), "procedure"),
        ("regenerative_endodontics", "rejeneratif endodonti", ("regenerative endodontics", "revascularization"), "procedure"),
        ("gutta_percha", "güta-perka", ("gutta-percha", "gutta percha"), "material"),
        ("sodium_hypochlorite", "sodyum hipoklorit", ("sodium hypochlorite", "NaOCl"), "material"),
        ("edta", "EDTA", ("ethylenediaminetetraacetic acid",), "material"),
    ),
    "periodontology": (
        ("gingival_recession", "gingival çekilme", ("gingival recession", "dişeti çekilmesi"), "finding"),
        ("gtr", "yönlendirilmiş doku rejenerasyonu", ("guided tissue regeneration", "GTR"), "procedure"),
        ("gbr", "yönlendirilmiş kemik rejenerasyonu", ("guided bone regeneration", "GBR"), "procedure"),
        ("root_planing", "kök yüzeyi düzleştirme", ("root planing",), "procedure"),
    ),
    "oral_surgery": (
        ("mronj", "ilaç ilişkili çene osteonekrozu", ("MRONJ", "medication-related osteonecrosis of the jaw"), "diagnosis"),
        ("sinus_lift", "sinüs tabanı yükseltme", ("sinus lift", "sinus floor augmentation"), "procedure"),
        ("ian_injury", "inferior alveolar sinir yaralanması", ("inferior alveolar nerve injury", "IAN injury"), "complication"),
        ("trismus", "trismus", ("trismus",), "complication"),
    ),
    "radiology": (
        ("bitewing", "bitewing radyografi", ("bitewing", "interproximal radiograph"), "imaging"),
        ("periapical_radiograph", "periapikal radyografi", ("periapical radiograph", "intraoral periapical"), "imaging"),
        ("cortication", "kortikasyon", ("cortication", "corticated border"), "finding"),
        ("trabeculation", "trabekülasyon", ("trabeculation", "trabecular pattern"), "finding"),
    ),
    "prosthodontics": (
        ("complete_denture", "tam protez", ("complete denture", "full denture"), "appliance"),
        ("rpd", "hareketli bölümlü protez", ("removable partial denture", "RPD"), "appliance"),
        ("fpd", "sabit bölümlü protez", ("fixed partial denture", "FPD"), "appliance"),
        ("kennedy_classification", "Kennedy sınıflaması", ("Kennedy classification",), "classification"),
        ("polyether", "polieter", ("polyether",), "material"),
    ),
    "restorative": (
        ("rmgic", "rezin modifiye cam iyonomer", ("resin-modified glass ionomer", "RMGIC"), "material"),
        ("polymerization", "polimerizasyon", ("polymerization", "light curing"), "procedure"),
        ("microleakage", "mikrosızıntı", ("microleakage",), "finding"),
        ("c_factor", "C-faktörü", ("C-factor", "configuration factor"), "measurement"),
    ),
    "pediatric_dentistry": (
        ("mih", "molar insizor hipomineralizasyonu", ("MIH", "molar incisor hypomineralization"), "diagnosis"),
        ("ssc", "paslanmaz çelik kron", ("stainless steel crown", "SSC"), "appliance"),
        ("mixed_dentition", "karışık dişlenme", ("mixed dentition",), "classification"),
    ),
    "oral_pathology": (
        ("oscc", "oral skuamöz hücreli karsinom", ("oral squamous cell carcinoma", "OSCC"), "diagnosis"),
        ("odontogenic_keratocyst", "odontojenik keratokist", ("odontogenic keratocyst", "OKC"), "diagnosis"),
        ("ameloblastoma_ext", "ameloblastoma", ("ameloblastoma",), "diagnosis"),
        ("mucocele", "mukosel", ("mucocele",), "diagnosis"),
    ),
    "dental_anesthesia": (
        ("lidocaine", "lidokain", ("lidocaine",), "material"),
        ("articaine", "artikain", ("articaine",), "material"),
        ("mepivacaine", "mepivakain", ("mepivacaine",), "material"),
        ("prilocaine", "prilokain", ("prilocaine",), "material"),
        ("epinephrine", "epinefrin", ("epinephrine", "adrenaline"), "material"),
        ("ianb", "inferior alveolar sinir bloğu", ("inferior alveolar nerve block", "IANB"), "procedure"),
        ("infiltration_anesthesia", "infiltrasyon anestezisi", ("infiltration anesthesia",), "procedure"),
        ("intraligamentary_anesthesia", "intraligamenter anestezi", ("intraligamentary anesthesia",), "procedure"),
        ("intrapulpal_anesthesia", "intrapulpal anestezi", ("intrapulpal anesthesia",), "procedure"),
        ("anesthetic_paresthesia", "lokal anestezi parestezisi", ("paresthesia", "parestezi"), "complication"),
    ),
}
