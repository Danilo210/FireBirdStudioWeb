import json, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from server import schema_sql, build_fdb

class GeneratorTest(unittest.TestCase):
    def setUp(self):
        self.project=json.loads((Path(__file__).parent/'sample.json').read_text())

    def test_generated_script(self):
        sql=schema_sql(self.project)
        self.assertIn('CREATE TABLE "CLIENTES"',sql)
        self.assertIn('"QUANTIDADE" INTEGER DEFAULT 1 NOT NULL',sql)
        self.assertIn('ON DELETE NO ACTION',sql)
        self.assertIn("'João Souza'",sql)

    def test_real_fdb(self):
        b=build_fdb(self.project)
        self.assertGreater(len(b),10000)

    def test_invalid_identifier(self):
        project=json.loads(json.dumps(self.project))
        project['tables'][0]['name']='BAD; DROP TABLE X'
        with self.assertRaises(ValueError): schema_sql(project)

    def test_invalid_numeric(self):
        project=json.loads(json.dumps(self.project))
        project['tables'][1]['records'][0]['PRECO']='123; DROP TABLE X'
        with self.assertRaises(ValueError): schema_sql(project)

if __name__ == '__main__': unittest.main()
