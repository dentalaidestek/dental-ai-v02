"""Held-out contrasts for the 1000-case fixes; expectations never use benchmark gold."""
import unittest
import json
from unittest.mock import patch
from app import study_retrieval_v2 as r
from app.academic_task_language import course_source_request, study_priority_request
from app.academic_request_slots import conversational_repair
from app.dental_query_intent import build_dental_requirement_plan as plan, classify_dental_intents, query_qualifiers

class RetrievalPlanSafetyTests(unittest.TestCase):
    def test_ready_chunk_metadata_compatibility_requires_literal_source_and_preserves_fields(self):
        meta=json.dumps({'nodes':['cyst'],'specialties':['oral_pathology'],'kinds':['diagnosis'],
                         'measurements':['5 mm'],'teeth':['26'],'imaging':['cbct'],'negated_nodes':['other']})
        def row(body):return (1,2,'Orto',1,1,'Kistler','TEXT',body,None,None,None,None,1,1,meta)
        with patch.object(r,'analyze_dental_text',side_effect=AssertionError('unrelated rows must stay indexed')):
            ordinary=r._row_semantic_features(row('Bu bir kisttir.'))
        self.assertEqual(ordinary.node_ids,('cyst',))
        cache={};added=r._row_semantic_features(row('Dentigeröz kist görülmedi.'),cache)
        self.assertIn('dentigerous_cyst',added.node_ids)
        self.assertIn('dentigerous_cyst',added.negated_node_ids)
        self.assertIn('other',added.negated_node_ids)
        self.assertEqual(added.measurements,('5 mm',))
        self.assertEqual(added.tooth_numbers,('26',))
        self.assertEqual(added.imaging_types,('cbct',))
        self.assertIs(r._row_semantic_features(row('ignored after cache'),cache),added)
        self.assertIn('maxillary_sinus',r._row_semantic_features(row('Maksiller sinus tabanı.')).node_ids)

    def test_scope_modifiers_cannot_erase_named_or_unknown_topics(self):
        old=[{'role':'USER','content':'Pulpitis anlat'}]
        for source in ('Ders notlarını','Bütün slaytları','Notların hepsini'):
            for style in ('kullanarak','ana başlıkları atlamadan','kısa ve anlaşılır'):
                query=f'{source} {style} soru hazırla'
                self.assertTrue(course_source_request(query),query)
                for topic in ('Nance apareyini','Zorbital sendromunu','Sodyum hipokloriti'):
                    query=f'Notlardaki {topic} kullanarak soru hazırla'
                    self.assertFalse(course_source_request(query),query)
                    resolved=r.resolve_followup_query(query,old)
                    self.assertNotIn('Pulpitis —',resolved)
                    self.assertTrue(plan(resolved).subject_terms or plan(resolved).subject_node_ids)

    def test_explicit_definition_is_retained_but_generic_closing_question_is_not(self):
        for topic in ('Pulpitis','Nance apareyi','Zorbital sendromu'):
            names={x.name for x in classify_dental_intents(f'{topic} tanımını açıkla, neden oluşur ve tedavisi nedir?')}
            self.assertTrue({'definition','cause','treatment'}.issubset(names),names)
            names={x.name for x in classify_dental_intents(f'{topic} tanısı ve tedavisi nedir?')}
            self.assertNotIn('definition',names)
            names={x.name for x in classify_dental_intents(f'{topic} tanımını anlatma; tedavisini anlat')}
            self.assertNotIn('definition',names)

    def test_age_correction_and_its_next_turn_keep_only_new_population(self):
        for first,second in (('Çocukları','erişkinleri'),('Çocuklarda','erişkinlerde'),('Erişkinleri','çocukları')):
            rejected='çocuk' if first.startswith('Çocuk') else 'erişkin'
            positive='erişkin' if rejected=='çocuk' else 'çocuk'
            q=f'{first} değil {second} açısından anlat'
            self.assertEqual(set(query_qualifiers(q)),{positive})
            history=[{'role':'USER','content':f'{first} pulpitis hakkında anlat'},
                     {'role':'USER','content':q}]
            resolved=r.resolve_followup_query('Aynı konudan devam et',history)
            self.assertIn('pulpitis',resolved.casefold())
            self.assertIn(positive,query_qualifiers(resolved))
            self.assertNotIn(rejected,query_qualifiers(resolved))
        p=plan('Çocukları değil erişkinleri pulpitis açısından anlat')
        self.assertTrue(all('çocuk' not in values for _,values in p.subject_qualifiers))
        self.assertIn('çocuk',query_qualifiers('Çocuklarda uygulanmaz mı?'))
        self.assertEqual(set(query_qualifiers('Çocukları ve erişkinleri karşılaştır')),{'çocuk','erişkin'})

    def test_relative_navigation_does_not_override_new_named_subject(self):
        history=[{'role':'USER','content':'Flor anlat'},{'role':'USER','content':'Pulpitis anlat'}]
        resolved=r.resolve_followup_query('Bir önceki konuya dön, daha sade açıkla',history)
        self.assertIn('Flor —',resolved)
        self.assertNotIn('Pulpitis —',resolved)
        for query in ('Önceki konudaki Nance apareyini anlat','Şimdi maksiller sinüs konusuna geçelim'):
            resolved=r.resolve_followup_query(query,history)
            self.assertNotIn('Flor —',resolved)
            self.assertNotIn('Pulpitis —',resolved)
        self.assertEqual(r.resolve_followup_query('Bir önceki konuya dön, daha basit anlat',[]),
                         'Bir önceki konuya dön, daha basit anlat')

    def test_annotation_manner_retains_named_subject_and_rejects_clinical_color(self):
        for mark in ('Maviyle yazılan','Kalın yazılmış','Kırmızıyla yazılan','kalin yazilmis','maviyle yazilan'):
            q=f'{mark} pulpitis başlığını anlat'
            self.assertIsNone(study_priority_request(q))
            p=plan(q)
            self.assertIn('pulpitis',p.subject_node_ids)
            self.assertTrue(p.requires_visual_source)
        for q in ('Sarı humma nedir','Kırmızı lezyonu anlat','Yıldız sendromunu açıkla','Kalın kanal ne demek'):
            self.assertIsNone(study_priority_request(q))
            self.assertFalse(plan(q).requires_visual_source,q)
            self.assertTrue(plan(q).subject_terms or plan(q).subject_node_ids)

    def test_specific_entities_and_generic_queries_stay_distinct(self):
        for q in ('Dentigeröz kist nedir','Dentigerous cyst nasıl görünür','Foliküler kist anlat'):
            self.assertIn('dentigerous_cyst',plan(q).subject_node_ids)
        self.assertEqual(plan('Kist nedir').subject_node_ids,('cyst',))
        self.assertIn('maxillary_sinus',plan('Maksiller sinüs nedir').subject_node_ids)
        self.assertNotIn('sna',plan('Maksiller sinüs nedir').subject_node_ids)
        self.assertIn('sna',plan('SNA açısı nedir').subject_node_ids)

    def test_nested_politeness_preserves_tasks_and_named_contrasts(self):
        history=[{'role':'USER','content':'Pulpitis anlat'}]
        for prefix in ('Kral rica etsem ','Rica etsem hocam ','Mümkünse kral '):
            q=prefix+'her başlığı tek bir paragrafla anlat'
            self.assertIn('Pulpitis',r.resolve_followup_query(q,history))
            self.assertTrue(conversational_repair(prefix+'beni anlamıyosun'))
            q=prefix+'Nance apareyini açıkla'
            self.assertIn('Nance',' '.join(plan(q).subject_terms))
            self.assertNotIn('Pulpitis —',r.resolve_followup_query(q,history))

if __name__=='__main__':unittest.main()
