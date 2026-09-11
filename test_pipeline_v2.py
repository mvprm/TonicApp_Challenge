import csv
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from poc import Extraction, ROOT, load_reference, validate_and_link, preprocess, detect_language
from build_references import snomed_concepts


def extraction(text, typ='diagnostic_test', **kwargs):
    return Extraction.model_validate({'entities':[{'text':text,'type':typ,
        'assertion':{'polarity':'negated','temporality':'historical','experiencer':'patient','context':'patient_specific'},
        'modifiers':kwargs.get('modifiers',[])}],'needs_context':False})


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.index, _ = load_reference(ROOT/'references.json')

    def test_preprocessing_preserves_negation_units_accents(self):
        raw='  Não\t há febre.\r\nDose: 5 mg; 3,5 mmol/L.\x00'
        self.assertEqual(preprocess(raw),'Não há febre. Dose: 5 mg; 3,5 mmol/L.')
        self.assertIn('\t',raw)

    def test_assertion_dimensions_independent(self):
        e,_=validate_and_link('asthma',extraction('asthma','pathology'),self.index)
        self.assertEqual(e[0]['assertion']['polarity'],'negated')
        self.assertEqual(e[0]['assertion']['temporality'],'historical')

    def test_language_short_text_abstains(self):
        self.assertEqual(detect_language('HbA1c 7%')['code'],'und')

    def test_languages(self):
        for code,text in [('pt','O doente apresenta febre e não tem antecedentes de doença respiratória.'),
                          ('es','El paciente presenta fiebre y no tiene antecedentes de enfermedad respiratoria.'),
                          ('it','Il paziente presenta febbre e non ha una storia di malattia respiratoria.'),
                          ('fr',"Le patient présente de la fièvre et ne présente aucun antécédent de maladie respiratoire.")]:
            with self.subTest(code=code): self.assertEqual(detect_language(text)['code'],code)

    def test_loinc_full_name_matches(self):
        text='Creatinine [Mass/volume] in Serum or Plasma'
        e,_=validate_and_link(text,extraction(text),self.index)
        self.assertEqual(e[0]['reference_id'],'LOINC:2160-0')

    def test_loinc_component_abstains_even_single_candidate(self):
        c=next(c for c in self.data['concepts'] if c['id']=='LOINC:2160-0')
        e,_=validate_and_link('Creatinine',extraction('Creatinine'),{('diagnostic_test','creatinine'):{c['id']:c}})
        self.assertIsNone(e[0]['reference_id'])
        self.assertEqual(e[0]['match_status'],'insufficient_specificity')

    def test_loinc_source_fields_and_locales(self):
        c=next(c for c in self.data['concepts'] if c['id']=='LOINC:2160-0')
        self.assertEqual(c['source_record']['LOINC_NUM'],'2160-0')
        self.assertNotIn('pt-PT',c['linguistic_variants'])
        for locale,row in c['linguistic_variants'].items():
            text=row['LONG_COMMON_NAME']
            if text:
                e,_=validate_and_link(text,extraction(text),self.index)
                self.assertEqual(e[0]['reference_id'],c['id'])

    def test_modifier_evidence_and_relation_review(self):
        ext=extraction('asthma','pathology',modifiers=[{'type':'severity','text':'severe','value':'severe'}])
        e,issues=validate_and_link('severe asthma',ext,self.index)
        self.assertEqual(e[0]['modifiers'][0]['start'],0)
        self.assertIn('modifier_relation_requires_review:severity',issues)
        e,issues=validate_and_link('asthma',ext,self.index)
        self.assertEqual(e[0]['modifiers'],[])

    def test_local_procedure_not_snomed(self):
        e,_=validate_and_link('apendicectomia',extraction('apendicectomia','procedure'),self.index)
        self.assertEqual(e[0]['reference_source'],'LOCAL_AUTHORED')

    def test_rf2_active_subset_and_inactive_rejection(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'synthetic.zip'
            with zipfile.ZipFile(path,'w') as z:
                z.writestr('Snapshot/Terminology/sct2_Concept_Snapshot_TEST.txt','id\teffectiveTime\tactive\n100\t20260101\t1\n200\t20260101\t0\n')
                z.writestr('Snapshot/Terminology/sct2_Description_Snapshot_TEST.txt','id\tconceptId\tactive\ttypeId\tterm\tlanguageCode\n1\t100\t1\t900000000000003001\tSynthetic procedure (procedure)\ten\n2\t100\t0\t1\tInactive synonym\ten\n')
            result=snomed_concepts(path,{'100':'procedure'})
            self.assertEqual(result[0]['aliases'],['Synthetic procedure (procedure)'])
            with self.assertRaises(ValueError): snomed_concepts(path,{'200':'procedure'})


if __name__=='__main__': unittest.main()
