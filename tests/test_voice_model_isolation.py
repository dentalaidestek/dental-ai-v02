"""Voice test doubles must coexist with models loaded by full-site collection."""
import os
from pathlib import Path
import subprocess
import sys


def test_voice_models_do_not_collide_with_existing_application_metadata():
    code = '''
from sqlmodel import SQLModel, Field
class ExistingUser(SQLModel, table=True):
    __tablename__ = 'user'
    id: int | None = Field(default=None, primary_key=True)
import test_voice_exam as voice_tests
assert voice_tests.User.metadata is not SQLModel.metadata
assert SQLModel.metadata.tables['user'] is ExistingUser.__table__
assert voice_tests.WorkJob.__table__.metadata is voice_tests.User.metadata
'''
    env = dict(os.environ)
    env['PYTHONPATH'] = str(Path('tests').resolve()) + os.pathsep + env.get('PYTHONPATH', '')
    result = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
