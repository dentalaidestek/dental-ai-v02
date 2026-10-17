"""Inventory source routes and async blocking-I/O hints; not a vulnerability scanner."""
import ast
import json
from pathlib import Path


def inventory():
    routes, hints = [], []
    files = sorted(Path('app').rglob('*.py'))
    markers = {'Session', 'open', 'storage_persist_file', 'storage_ensure_local',
               '_copy_validated_image', '_copy_validated_analysis_image'}
    for path in files:
        source = path.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and (
                        decorator.func.attr in {'get', 'post', 'put', 'patch', 'delete', 'websocket'}):
                    routes.append(dict(file=str(path), line=node.lineno, name=node.name,
                        method=decorator.func.attr.upper(),
                        path_expression=ast.unparse(decorator.args[0]) if decorator.args else None))
            if isinstance(node, ast.AsyncFunctionDef):
                calls = sorted({call.func.id for call in ast.walk(node)
                    if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id in markers})
                if calls:
                    hints.append(dict(file=str(path), line=node.lineno, name=node.name, direct_calls=calls))
    return {'python_files': len(files), 'source_route_declarations': len(routes),
            'caveat': 'Source declarations include unmounted compatibility routes. Hints require manual review; ownership and runtime authorization are not proved.',
            'routes': routes, 'async_io_review_hints': hints}


if __name__ == '__main__':
    output = Path('evaluation/system/surface_20261017.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    result = inventory()
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'routes'}, ensure_ascii=False, indent=2))
