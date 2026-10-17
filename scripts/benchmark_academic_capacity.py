"""Compare real route SQL on synthetic ownership data; not a live load test.

Run from repository root with tests/dependencies available. The optional
--baseline is a separately preserved pre-change main.py, never production data.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import statistics
import tempfile
import time
from datetime import datetime

from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline')
    parser.add_argument('--output', default='tmp/academic_capacity_benchmark.json')
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('capacity_tests', 'tests/test_academic_capacity.py')
    support = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(support)
    Course, Material, Message = support.CapacityCourse, support.CapacityMaterial, support.CapacityMessage
    with tempfile.TemporaryDirectory() as directory:
        engine = create_engine('sqlite:///' + str(Path(directory) / 'synthetic.db'))
        SQLModel.metadata.create_all(engine, tables=[Course.__table__, Material.__table__, Message.__table__])
        stamp = datetime(2026, 10, 17)
        with engine.begin() as conn:
            # 60,000 distinct owner IDs, one course each. Owner 1 also has a
            # long history and 200 extra courses. This is not 60k active clients.
            for start in range(1, 60001, 2000):
                conn.execute(Course.__table__.insert(), [dict(id=i, owner_user_id=i,
                    title=f'Synthetic course {i}', description='', updated_at=stamp)
                    for i in range(start, start + 2000)])
                conn.execute(Material.__table__.insert(), [dict(id=i, course_id=i,
                    owner_user_id=i, created_at=stamp) for i in range(start, start + 2000)])
            conn.execute(Course.__table__.insert(), [dict(id=i, owner_user_id=1,
                title=f'Additional course {i}', description='', updated_at=stamp) for i in range(60001, 60201)])
            conn.execute(Material.__table__.insert(), [dict(id=i, course_id=i,
                owner_user_id=1, created_at=stamp) for i in range(60001, 60201)])
            conn.execute(Message.__table__.insert(), [dict(id=i, course_id=1,
                owner_user_id=1, content='Synthetic explanation. ' * 45) for i in range(1, 5001)])
        metrics = {'sql': 0, 'messages_loaded': 0}
        def sql(*a): metrics['sql'] += 1
        def loaded(*a): metrics['messages_loaded'] += 1
        event.listen(engine, 'before_cursor_execute', sql)
        event.listen(Message, 'load', loaded)
        results = []
        try:
            paths = ([('before', args.baseline)] if args.baseline else []) + [('after', 'app/main.py')]
            for version, path in paths:
                for name, arguments in [('study_notes_index', (None,)),
                        ('study_ai_page', (None, 1, None)), ('study_course_detail', (None, 1))]:
                    route = support.handler(name, engine, path=path)
                    samples = []
                    for _ in range(5):
                        metrics.update(sql=0, messages_loaded=0)
                        start = time.perf_counter()
                        result = route(*arguments)
                        samples.append(round((time.perf_counter()-start)*1000, 3))
                    results.append(dict(version=version, route=name, median_ms=statistics.median(samples),
                        queries=metrics['sql'], message_objects_loaded=metrics['messages_loaded'],
                        response_items=len(result.get('course_cards', result.get('messages', [])))))
        finally:
            event.remove(Message, 'load', loaded)
            engine.dispose()
        output = {'dataset': {'distinct_owner_ids': 60000, 'courses': 60200, 'messages_on_active_course': 5000},
                  'limits': 'SQLite, warm local process; auth/readiness/templates stubbed. No PostgreSQL, network, LLM or 60k concurrency.',
                  'results': results}
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
