"""Curated dental terminology for deterministic Academic V2 retrieval.

Aliases are equivalence-level only: translations, accepted abbreviations and
common lecture-note variants. Related concepts are deliberately not mixed into
the same alias set because that would lower retrieval precision.
"""

DENTAL_ALIAS_GROUPS = (
    # Orthodontics / cephalometrics
    ("SNA", "sella nasion A", "sella-nasion-A"),
    ("SNB", "sella nasion B", "sella-nasion-B"),
    ("ANB", "A-N-B", "A point nasion B point"),
    ("Wits", "Wits appraisal", "Wits analizi"),
    ("Frankfort horizontal", "FH düzlemi", "Frankfort düzlemi"),
    ("mandibular plane", "mandibular düzlem", "GoGn", "Go-Gn"),
    ("alt çene geriliği", "mandibular retrognati", "mandibular retrognathia"),
    ("üst çene geriliği", "maksiller retrognati", "maxillary retrognathia"),
    ("alt çene ileriliği", "mandibular prognati", "mandibular prognathism"),
    ("üst çene ileriliği", "maksiller prognati", "maxillary prognathism"),
    ("derin kapanış", "deep bite", "deep overbite", "örtülü kapanış"),
    ("açık kapanış", "open bite"),
    ("çapraz kapanış", "crossbite", "cross bite"),
    ("Sınıf I", "Class I", "Angle Class I"),
    ("Sınıf II", "Class II", "Angle Class II"),
    ("Sınıf III", "Class III", "Angle Class III"),
    ("overjet", "horizontal overlap", "yatay örtüşme"),
    ("overbite", "vertical overlap", "dikey örtüşme"),
    ("sefalometri", "cephalometry", "sefalometrik", "cephalometric"),

    # Endodontics
    ("kanal tedavisi", "root canal treatment", "endodontik tedavi"),
    ("çalışma boyu", "working length", "WL"),
    ("apikal konstriksiyon", "apical constriction", "minor diameter"),
    ("apikal foramen", "apical foramen", "major diameter"),
    ("kök kanal sistemi", "root canal system"),
    ("pulpa nekrozu", "pulp necrosis", "necrotic pulp"),
    ("geri dönüşümlü pulpitis", "reversible pulpitis"),
    ("geri dönüşümsüz pulpitis", "irreversible pulpitis"),
    ("periapikal lezyon", "periapical lesion", "kök çevresi lezyon"),
    ("kök rezorpsiyonu", "root resorption", "rezorpsiyon"),

    # Periodontology
    ("sondalama derinliği", "probing depth", "PD"),
    ("klinik ataşman kaybı", "clinical attachment loss", "CAL"),
    ("sondalamada kanama", "bleeding on probing", "BOP"),
    ("diş taşı", "dental calculus", "calculus", "kalkulus"),
    ("furkasyon", "furcation", "bifurkasyon"),
    ("alveol kemiği", "alveolar bone", "alveolar process"),
    ("kemik kaybı", "bone loss", "alveolar bone loss"),
    ("diş eti", "gingiva", "gingival"),

    # Oral surgery / radiology
    ("yirmi yaş dişi", "üçüncü molar", "third molar", "wisdom tooth"),
    ("gömülü diş", "impacted tooth", "impakte diş"),
    ("inferior alveolar sinir", "inferior alveolar nerve", "IAN"),
    ("mandibular kanal", "mandibular canal", "inferior alveolar canal"),
    ("radyolüsent", "radiolucent", "radiolucency"),
    ("radyopak", "radiopaque", "radiopacity"),
    ("CBCT", "cone beam computed tomography", "konik ışınlı bilgisayarlı tomografi"),
    ("panoramik radyografi", "panoramic radiograph", "OPG", "orthopantomogram"),

    # Prosthodontics / materials
    ("dikey boyut", "vertical dimension", "VDO", "vertical dimension of occlusion"),
    ("sentrik ilişki", "centric relation", "CR"),
    ("maksimum interküspidasyon", "maximum intercuspation", "MIP"),
    ("ölçü maddesi", "impression material"),
    ("aljinat", "alginate", "irreversible hydrocolloid"),
    ("polivinil siloksan", "polyvinyl siloxane", "PVS", "addition silicone"),
    ("cam iyonomer siman", "glass ionomer cement", "GIC"),

    # Restorative / cariology
    ("çürük", "karies", "caries", "dental caries"),
    ("mine", "enamel"),
    ("dentin", "dentine"),
    ("smear layer", "smear tabakası"),
    ("asit pürüzlendirme", "acid etching", "etching"),

    # Pediatric dentistry
    ("süt dişi", "primer diş", "primary tooth", "deciduous tooth"),
    ("daimi diş", "permanent tooth", "kalıcı diş"),
    ("erken çocukluk çağı çürüğü", "early childhood caries", "ECC"),

    # Anatomy / occlusion / TMD
    ("çene eklemi", "temporomandibular joint", "temporomandibular", "TME", "TMJ"),
    ("kondil", "condyle", "mandibular condyle"),
    ("artiküler disk", "articular disc", "eklem diski"),
    ("oklüzyon", "occlusion"),
    ("kök ucu", "apex", "apeks", "apikal", "periapikal"),
)
