"""Exercise /proc exit races without importing or accessing board MMIO."""
from pathlib import Path
import ast,json,types
R=Path(__file__).resolve().parent
node=next(n for n in ast.parse((R/'pause_preview_board.py').read_text()).body
          if isinstance(n,ast.FunctionDef) and n.name=='wait_key_exit')
code=compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(R/'pause_preview_board.py'),'exec')
records=[]
for name,values,expected in [
    ('zombie',['R','Z'],None),
    ('proc_path_removed',[FileNotFoundError()],None),
    ('proc_reaped_during_read',['R',ProcessLookupError(3,'No such process')],None),
    ('pid_reused',[AssertionError('Camera/key PID was reused')],AssertionError),
    ('permission_error',[PermissionError()],PermissionError),
    ('still_running',['R']*100,TimeoutError)]:
    states=iter(values)
    def state(_):
        value=next(states)
        if isinstance(value,Exception):raise value
        return value
    namespace={'process_state':state,'time':types.SimpleNamespace(sleep=lambda _:None)}
    exec(code,namespace)
    try:
        namespace['wait_key_exit']({'pid':123})
        assert expected is None
    except Exception as exc:
        assert expected is not None and isinstance(exc,expected),(name,exc)
    records.append(dict(case=name,passed=True))
(R/'key_exit_verified.json').write_text(json.dumps(dict(passed=True,cases=records,hardware_access=False),indent=2))
print('KEY_EXIT_RACE_AND_PID_GUARDS_PASS')
