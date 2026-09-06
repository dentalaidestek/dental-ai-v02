import json


SYSTEM_PROMPT = """
Sen yalnızca DİŞ HEKİMLİĞİ alanında çalışan bir klinik karar destek yapay zekasısın.

TEMEL AMAÇ:
Hekime, mevcut klinik bilgiler ve yüklenen dental görüntü üzerinden
mümkün olduğunca güçlü, yapılandırılmış ve kanıta dayalı klinik karar
desteği vermek.

ÖNCELİK SIRASI:
1. Görüntüde gerçekten gözlenen bulgular
2. Diş numarası ve hekimin klinik bilgileri
3. Hekimin verdiği ek cevaplar
4. Güvenilir dental bilgi tabanından gelen kanıtlar

GÖRÜNTÜ ANALİZİ:

Görüntü verildiyse görüntüyü gerçekten incele.

Önce yalnızca görüntüde gözlenebilen somut bulguları belirle.

Örneğin uygun olduğunda:
- radyolüsensi / radyopak alan
- lezyonun yaklaşık konumu
- mine/dentin tutulumu
- pulpa ile ilişkisi
- periapikal değişiklik
- periodontal kemik kaybı
- restorasyon
- restorasyon çevresindeki değişiklik
- kırık veya yapısal düzensizlik
- kök ve çevre dokularla ilişkili görünüm
- görüntü kalitesi
- görüntünün tanısal yeterliliği

Bunlardan yalnızca görüntüde gerçekten desteklenenleri belirt.

Görüntüde görülmeyen hiçbir bulguyu varmış gibi yazma.

Görüntü kalitesi veya açı nedeniyle bir bulgu değerlendirilemiyorsa
bunu açıkça belirt.

GÖRÜNTÜDEN TANIYA GEÇİŞ:

Önce:
GÖZLENEBİLEN BULGU

Sonra:
BU BULGULARLA UYUMLU KLİNİK OLASILIKLAR

Sonra:
EN OLASI KLİNİK DURUM

Sonra:
AYIRICI TANI

Kaynaklardan gelen bilgi, görüntü bulgularını destekleyebilir veya
zayıflatabilir; ancak kaynakta geçen bir durum yalnızca kaynakta
geçtiği için hastada var kabul edilmez.

BENZERLİK MANTIĞI:

Bilgi tabanında bu vakayla ilişkili dental bilgi varsa onu kullan.

Ancak yalnızca metinsel benzerlik nedeniyle görüntünün aynı hastalık
olduğunu iddia etme.

Kaynak bilgisi görüntüdeki bulguların klinik yorumlanmasına yardımcı
olmalıdır.

SORULAR:

Ön değerlendirmede yalnızca tanısal değerlendirmeyi veya tedavi
yaklaşımını gerçekten değiştirecek eksik bilgileri sor.

- Gereksiz soru sorma.
- Verilmiş bilgiyi tekrar sorma.
- Aynı bilgiyi farklı sorularla tekrar sorma.
- Maksimum 5 soru.
- Kritik bilgi yeterliyse READY döndür.
- Acil güvenlik açısından önemli bilgi gerekiyorsa onu önceliklendir.

SORU TİPLERİ:

VAR_YOK:
Bir durumun mevcut olup olmadığını sor.

SCALE:
Şiddet veya derece için kullan.
Varsayılan 1-10.

TEXT:
Açıklama gerçekten gerekiyorsa kullan.

NUMBER:
Gerçek sayısal bilgi gerekiyorsa kullan.

CHOICE:
Belirli seçenekler arasında klinik olarak anlamlı ayrım varsa kullan.

KLİNİK SINIR:

Hekimin klinik muayenesinin yerini alma.

Ancak yalnızca genel tavsiye vermekle yetinme.

Mevcut bilgiler yeterliyse:
- en olası klinik durumu belirle,
- ayırıcı tanıları sırala,
- önemli görüntü ve klinik bulguları belirt,
- uygun tedavi seçeneklerini değerlendir,
- mevcut bilgiler ışığında tercih edilen yaklaşımı belirt.

Kesinlik derecesini belirsizlik alanında açıkla.

Hasta hakkında verilmemiş bilgi uydurma.

FİLM / RÖNTGEN:

Görüntü yoksa radyografik bulgu uydurma.

Görüntü varsa görüntüdeki bulguları kendin analiz et.

"Görüntüyü hekim yorumlamalı" şeklinde görüntü analizinden kaçınma.

Görüntü tanısal açıdan yetersizse neden yetersiz olduğunu açıkla.

TEDAVİ:

Tedaviyi yalnızca genel tavsiye şeklinde bırakma.

Mevcut görüntü + klinik bilgi + cevaplar + bilgi tabanı doğrultusunda
uygun seçenekleri değerlendir.

En uygun yaklaşımı ayrıca belirt.

Tedaviyi hastaya özgü kesin reçete gibi sunma.
"""


def _clean(text):
    if not text:
        return ""
    return str(text).strip()


def build_preliminary_prompt(
    tooth_number,
    clinical_notes,
    image_path=None,
    knowledge_context=""
):
    return f"""
{SYSTEM_PROMPT}

DENTAL VAKA ANALİZİ YAP.

Diş: {_clean(tooth_number)}

Klinik bilgi:
{_clean(clinical_notes)}

Görüntü:
{
    "Görüntüyü gerçekten incele. Sadece görüntüde gördüğün bulguları yaz."
    if image_path
    else
    "Görüntü yok. Görüntü bulgusu yazma."
}

Bilgi tabanı:
{knowledge_context}

Bilgi tabanını kopyalama. Kanıtları anlayıp vakaya uygun kısa Türkçe
klinik değerlendirme yap.

ÇIKTIYI ÇOK KISA TUT.
SADECE GEÇERLİ JSON DÖNDÜR.
Markdown kullanma.

ŞU YAPIDA OL:

{{
  "status": "ANALYSIS_COMPLETE",
  "most_likely": "En olası durum ve kısa gerekçe.",
  "differential": ["Olasılık 1", "Olasılık 2"],
  "findings": ["Görüntüde görülen objektif bulgu 1", "Görüntüde görülen objektif bulgu 2"],
  "treatment_options": ["Tedavi seçeneği 1", "Tedavi seçeneği 2"],
  "recommended_evaluation": ["Gerekli ek değerlendirme"],
  "questions": [
    {{
      "question": "Kararı değiştirebilecek kritik soru",
      "type": "VAR_YOK"
    }}
  ],
  "preferred_approach": "Mevcut bilgilerle tercih edilen yaklaşım.",
  "uncertainty": "Belirsizlik ve hekim tarafından doğrulanması gereken nokta."
}}

KURALLAR:
- Her metin kısa olsun.
- Her liste en fazla 2 madde olsun.
- questions en fazla 3 soru olsun.
- Gereksiz soru sorma.
- Sorular sadece klinik kararı değiştirecek bilgileri sorsun.
- Görüntüde olmayan bulgu uydurma.
- Görüntü yoksa radyografik bulgu yazma.
- Tedavi seçeneklerini kısa yaz.
- JSON'u mutlaka tamamen kapat.
"""


def build_final_prompt(
    tooth_number,
    clinical_notes,
    answers,
    image_path=None,
    knowledge_context=""
):
    return f"""
{SYSTEM_PROMPT}

DENTAL VAKA NİHAİ ANALİZİ YAP.

Diş:
{_clean(tooth_number)}

İlk klinik bilgi:
{_clean(clinical_notes)}

Hekimin yeni cevapları:
{json.dumps(answers, ensure_ascii=False)}

Görüntü:
{
    "Görüntüyü gerçekten incele. Yalnızca görüntüde desteklenen objektif bulguları yaz."
    if image_path
    else
    "Görüntü yok. Görüntü bulgusu yazma."
}

Bilgi tabanı:
{knowledge_context}

Görüntü bulgularını, diş numarasını, ilk klinik bilgiyi,
hekimin yeni cevaplarını ve bilgi tabanını birlikte değerlendir.

Bilgi tabanını kopyalama. Kanıtları anlayıp vakaya uygun kısa
Türkçe klinik değerlendirme yap.

SADECE GEÇERLİ JSON DÖNDÜR.
Markdown kullanma.
Çok kısa yaz.

JSON YAPISI:

{{
  "status": "FINAL",
  "most_likely": "En olası durum ve kısa gerekçe.",
  "differential": [
    "Ayırıcı olasılık 1",
    "Ayırıcı olasılık 2"
  ],
  "findings": [
    "Görüntüde objektif olarak görülen bulgu 1",
    "Görüntüde objektif olarak görülen bulgu 2"
  ],
  "treatment_options": [
    "Tedavi seçeneği 1",
    "Tedavi seçeneği 2"
  ],
  "preferred_approach": "Mevcut bilgiler ışığında tercih edilen kısa yaklaşım."
}}

KURALLAR:
- Her metin kısa olsun.
- Her liste en fazla 2 madde olsun.
- Görüntüde olmayan bulgu uydurma.
- Görüntü varsa gerçekten görüntüyü analiz et.
- Görüntü yoksa radyografik bulgu yazma.
- Klinik bilgiyi görüntü bulgusu gibi gösterme.
- Tedavi seçeneklerini kısa yaz.
- Soru sorma.
- recommended_evaluation alanı oluşturma.
- uncertainty alanı oluşturma.
- JSON'u mutlaka tamamen kapat.
"""

def parse_ai_result(text):
    """
    AI çıktısını güvenli şekilde JSON'a çevirir.
    Markdown json çitlerini kaldırır ve geçerli JSON
    bulunamazsa RAW döndürür.
    """

    if not text:
        return {
            "status": "AI_INVALID",
            "error": "AI boş cevap döndürdü."
        }

    cleaned = text.strip()

    if cleaned.startswith("```"):
        lines = cleaned.splitlines()

        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        cleaned = "\n".join(lines).strip()

    try:
        result = json.loads(cleaned)

        if isinstance(result, dict):
            status = result.get("status")

            if status == "ANALYSIS_COMPLETE":
                result["status"] = "INITIAL"

            return result

    except json.JSONDecodeError:
        pass

    # Cevabın içinde JSON nesnesi varsa bulmayı dene.
    first = cleaned.find("{")
    last = cleaned.rfind("}")

    if first != -1 and last > first:
        candidate = cleaned[first:last + 1]

        try:
            result = json.loads(candidate)

            if isinstance(result, dict):
                if result.get("status") == "ANALYSIS_COMPLETE":
                    result["status"] = "INITIAL"

                return result

        except json.JSONDecodeError:
            pass

    return {
        "status": "RAW",
        "text": text
    }



# Gemini generateContent structured-output şemaları.
# Bunlar yalnızca çıktı biçimini sabitler; klinik içerik kuralları promptta kalır.
PRELIMINARY_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "status": {"type": "STRING", "enum": ["ANALYSIS_COMPLETE"]},
        "most_likely": {"type": "STRING"},
        "differential": {"type": "ARRAY", "items": {"type": "STRING"}, "maxItems": 2},
        "findings": {"type": "ARRAY", "items": {"type": "STRING"}, "maxItems": 2},
        "treatment_options": {"type": "ARRAY", "items": {"type": "STRING"}, "maxItems": 2},
        "recommended_evaluation": {"type": "ARRAY", "items": {"type": "STRING"}, "maxItems": 2},
        "questions": {
            "type": "ARRAY",
            "maxItems": 3,
            "items": {
                "type": "OBJECT",
                "properties": {
                    "question": {"type": "STRING"},
                    "type": {
                        "type": "STRING",
                        "enum": ["VAR_YOK", "SCALE", "TEXT", "NUMBER", "CHOICE"],
                    },
                },
                "required": ["question", "type"],
            },
        },
        "preferred_approach": {"type": "STRING"},
        "uncertainty": {"type": "STRING"},
    },
    "required": [
        "status",
        "most_likely",
        "differential",
        "findings",
        "treatment_options",
        "recommended_evaluation",
        "questions",
        "preferred_approach",
        "uncertainty",
    ],
}

FINAL_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "status": {"type": "STRING", "enum": ["FINAL"]},
        "most_likely": {"type": "STRING"},
        "differential": {"type": "ARRAY", "items": {"type": "STRING"}, "maxItems": 2},
        "findings": {"type": "ARRAY", "items": {"type": "STRING"}, "maxItems": 2},
        "treatment_options": {"type": "ARRAY", "items": {"type": "STRING"}, "maxItems": 2},
        "preferred_approach": {"type": "STRING"},
    },
    "required": [
        "status",
        "most_likely",
        "differential",
        "findings",
        "treatment_options",
        "preferred_approach",
    ],
}


_ALLOWED_QUESTION_TYPES = {"VAR_YOK", "SCALE", "TEXT", "NUMBER", "CHOICE"}


def _invalid_result(message):
    return {
        "status": "AI_INVALID",
        "error": message,
    }


def _valid_text(value):
    return isinstance(value, str) and bool(value.strip())


def _valid_string_list(value):
    return isinstance(value, list) and all(_valid_text(item) for item in value)


def validate_preliminary_result(result):
    """Ön analiz JSON'unu template'e verilmeden önce doğrular ve normalize eder."""
    if not isinstance(result, dict):
        return _invalid_result("AI beklenen klinik sonuç formatını oluşturamadı.")

    if result.get("status") not in {"ANALYSIS_COMPLETE", "INITIAL"}:
        return _invalid_result("AI beklenen ön analiz durumunu üretmedi.")

    for field in ("most_likely", "preferred_approach", "uncertainty"):
        if not _valid_text(result.get(field)):
            return _invalid_result(f"AI ön analizinde '{field}' alanı eksik veya geçersiz.")

    for field in (
        "differential",
        "findings",
        "treatment_options",
        "recommended_evaluation",
    ):
        if not _valid_string_list(result.get(field)):
            return _invalid_result(f"AI ön analizinde '{field}' alanı eksik veya geçersiz.")
        result[field] = result[field][:2]

    questions = result.get("questions")
    if not isinstance(questions, list):
        return _invalid_result("AI ön analizindeki soru listesi geçersiz.")

    clean_questions = []
    for item in questions[:5]:
        if not isinstance(item, dict):
            continue
        question = item.get("question")
        question_type = item.get("type")
        if not _valid_text(question) or question_type not in _ALLOWED_QUESTION_TYPES:
            continue
        clean_questions.append({
            "question": question.strip(),
            "type": question_type,
        })

    # Boş soru listesi geçerlidir; yeterli bilgi varsa model soru sormayabilir.
    result["questions"] = clean_questions
    result["status"] = "INITIAL"
    return result


def validate_final_result(result):
    """Nihai analiz JSON'unu doğrular ve yalnız geçerli ise FINAL kabul eder."""
    if not isinstance(result, dict):
        return _invalid_result("AI beklenen final sonuç formatını oluşturamadı.")

    if result.get("status") != "FINAL":
        return _invalid_result("AI beklenen final analiz durumunu üretmedi.")

    for field in ("most_likely", "preferred_approach"):
        if not _valid_text(result.get(field)):
            return _invalid_result(f"AI final analizinde '{field}' alanı eksik veya geçersiz.")

    for field in ("differential", "findings", "treatment_options"):
        if not _valid_string_list(result.get(field)):
            return _invalid_result(f"AI final analizinde '{field}' alanı eksik veya geçersiz.")
        result[field] = result[field][:2]

    result["status"] = "FINAL"
    return result
