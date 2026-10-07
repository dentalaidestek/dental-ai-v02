"""Language-only test harness: AST omits unavailable storage/DB imports.

Never use this for SQL, source scope integration or provider/browser evidence.
"""
import ast
import sys
import types
import os
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
source = Path(os.environ.get('DENTAL_PROBE_RETRIEVAL', str(root / 'app/study_retrieval_v2.py')))
tree = ast.parse(source.read_text())
skip = {'sqlmodel', 'sqlalchemy', 'app.object_cache', 'app.object_storage'}
tree.body = [n for n in tree.body if not isinstance(n, ast.ImportFrom) or n.module not in skip]
for node in tree.body:
    if isinstance(node, ast.FunctionDef):
        node.decorator_list = [d for d in node.decorator_list
                               if not isinstance(d, ast.Name) or d.id != 'storage_scoped']
module = types.ModuleType('app.study_retrieval_v2')
sys.modules[module.__name__] = module
exec(compile(tree, str(source), 'exec'), module.__dict__)

