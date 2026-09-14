import ast
import functools
import hashlib
import hmac
from pathlib import Path
from types import SimpleNamespace
import unittest

class AuthTests(unittest.TestCase):
    def test_missing_wrong_and_valid_credentials(self):
        tree = ast.parse(Path(__file__).with_name('main.py').read_text(encoding='utf-8-sig'))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'require_auth')
        request = SimpleNamespace(headers={})
        namespace = dict(functools=functools, hashlib=hashlib, hmac=hmac, request=request, jsonify=lambda value:value, API_KEY='')
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'auth-boundary', 'exec'), namespace)
        calls=[]
        protected=namespace['require_auth'](lambda:calls.append('called') or {'ok':True})
        self.assertEqual(protected()[1],503)
        token='synthetic-fixture-'+'x'*32
        namespace['API_KEY']=token
        for value in ['', 'Bearer wrong', 'Bearer é']:
            request.headers={'Authorization':value};self.assertEqual(protected()[1],401)
        self.assertEqual(calls,[])
        for headers in [{'Authorization':'Bearer '+token},{'X-API-Key':token}]:
            request.headers=headers;self.assertEqual(protected(),{'ok':True})
        self.assertEqual(len(calls),2)

    def test_all_non_health_routes_have_authentication(self):
        tree=ast.parse(Path(__file__).with_name('main.py').read_text(encoding='utf-8-sig'))
        for node in tree.body:
            if not isinstance(node,ast.FunctionDef):continue
            routes=[d for d in node.decorator_list if isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and d.func.attr=='route']
            if routes and node.name != 'health':
                self.assertTrue(any(isinstance(d,ast.Name) and d.id=='require_auth' for d in node.decorator_list),node.name)

if __name__ == '__main__': unittest.main()
