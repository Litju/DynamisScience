"""Compare the executable's embedded Python code with checkout source; emit a hashed receipt."""
from pathlib import Path
import hashlib, importlib.metadata, json, marshal, subprocess, sys
from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader
root=Path('D:/projects/DynamisScience')
out=Path('C:/Users/Usuario/AppData/Local/Temp/dynamis-independent-20261112')
exe=out/'delivery-dist/DynamisScience/DynamisScience.exe'
archive=CArchiveReader(str(exe))
pyz_name=next(k for k in archive.toc if k.endswith('.pyz'))
pyz=out/'embedded-application.pyz'
pyz.write_bytes(archive.extract(pyz_name))
reader=ZlibArchiveReader(str(pyz))
checks=[]
for name in sorted(reader.toc):
    if not (name.startswith('dynamis_science') or name=='scripts.res647_walkthrough'):
        continue
    path=root/'services/science'/Path(*name.split('.')).with_suffix('.py')
    if not path.exists():
        path=root/'services/science'/Path(*name.split('.'))/'__init__.py'
    assert path.is_file(), (name,path)
    code=reader.extract(name)
    compiled=compile(path.read_bytes(),code.co_filename,'exec',dont_inherit=True,optimize=0)
    assert code==compiled, f'Packaged code differs from source: {name}'
    checks.append({'module':name,'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'code_equal':True})
entry=marshal.loads(archive.extract('desktop_entry'))
assert entry==compile((root/'services/science/scripts/desktop_entry.py').read_bytes(),entry.co_filename,'exec',dont_inherit=True,optimize=0)
receipt={'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
 'application_tree':subprocess.check_output(['git','rev-parse','HEAD:services/science/dynamis_science'],cwd=root,text=True).strip(),
 'source_status':subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).splitlines(),
 'executable':str(exe),'executable_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'executable_bytes':exe.stat().st_size,
 'embedded_pyz_sha256':hashlib.sha256(pyz.read_bytes()).hexdigest(),'entry_code_equal':True,'modules':checks,
 'python':sys.version,'pyinstaller':importlib.metadata.version('pyinstaller')}
(out/'package-identity.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps({'code_equal_modules':len(checks),'executable_sha256':receipt['executable_sha256']}))

