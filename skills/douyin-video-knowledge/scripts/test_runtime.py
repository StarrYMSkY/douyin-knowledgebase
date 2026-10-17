"""Offline regression tests; never logs in, downloads models, or touches live jobs."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SKILL = Path(__file__).resolve().parents[1]
RUNTIME = SKILL/'assets/runtime'

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class RuntimeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)/'job'
        command = [sys.executable,str(SKILL/'scripts/initialize.py'),'--workspace',str(self.root),
                   '--profile','https://www.douyin.com/user/test-public-profile',
                   '--since','2025-01-02','--until','2025-01-03','--title','Test <title>']
        subprocess.run(command,check=True,capture_output=True)
        self.command = command
        sys.path.insert(0,str(self.root))
        sys.modules.pop('kb_config',None)
        self.cfg = load('kb_config',self.root/'kb_config.py')
        sys.modules['kb_config'] = self.cfg
        (self.root/'capture').mkdir()
        (self.root/'knowledge').mkdir()

    def tearDown(self):
        sys.path.remove(str(self.root))
        sys.modules.pop('kb_config',None)
        self.temp.cleanup()

    def write(self, relative, value):
        target=self.root/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')

    def test_initializer_refuses_overwrite(self):
        result=subprocess.run(self.command,capture_output=True)
        self.assertNotEqual(result.returncode,0)

    def test_range_uses_shanghai_and_exclusive_end(self):
        start, stop=self.cfg.bounds(self.cfg.config())
        self.write('capture/posts.json',[{'id':'1','create_time':start-1},
                  {'id':'2','create_time':start},{'id':'3','create_time':stop}])
        self.assertEqual([x['id'] for x in self.cfg.selected_posts()],['2'])
        self.assertEqual(stop-start,86400)

    def test_machine_comparison_retains_disagreement(self):
        pipeline=load('test_pipeline',self.root/'pipeline.py')
        segment=[{'start':0,'end':2,'text':'美债下降'}]
        rows=pipeline.compare(segment,[{'start':0,'end':2,'text':'美贷下降'}])
        self.assertEqual(rows[0]['status'],'needs_review')
        self.assertEqual(rows[0]['text'],'美债下降')
        self.assertEqual(pipeline.compare(segment,[])[0]['reason'],'OCR missing')
        match=pipeline.compare(segment,[{'start':0,'end':2,'text':'美债下降'}])
        self.assertEqual(match[0]['status'],'automatic_agreement')

    def test_audit_and_html(self):
        start,_=self.cfg.bounds(self.cfg.config())
        self.write('capture/posts.json',[{'id':'2','create_time':start}])
        self.write('capture/downloads.json',[{'id':'2','status':'downloaded'}])
        finish=load('test_finish',self.root/'finish_pipeline.py')
        self.assertFalse(finish.audit()['complete'])
        self.write('knowledge/2/source.json',{'id':'2','title':'</script><script>unsafe</script>',
                   'published_at':'2025-01-02T00:00:00+08:00','duration':2,'url':'https://www.douyin.com/video/2'})
        self.write('knowledge/2/asr.json',[{'text':'美债'}])
        self.write('knowledge/2/ocr.json',[{'text':'美债'}])
        self.write('knowledge/2/comparison.json',[{'start':0,'end':2,'text':'美债','ocr_text':'美债','status':'automatic_agreement'}])
        self.assertTrue(finish.audit()['complete'])
        subprocess.run([sys.executable,str(self.root/'build_index.py')],check=True,capture_output=True)
        html=(self.root/'knowledge/index.html').read_text(encoding='utf-8')
        self.assertIn('Test &lt;title&gt;',html)
        self.assertNotIn('</script><script>unsafe',html)
        self.assertNotIn('/ 226',html)
        self.write('knowledge/2/ocr.json',[])
        self.assertFalse(finish.audit()['complete'])

    def test_sources_compile(self):
        for path in RUNTIME.glob('*.py'):
            compile(path.read_text(encoding='utf-8'),str(path),'exec')

if __name__ == '__main__': unittest.main()
