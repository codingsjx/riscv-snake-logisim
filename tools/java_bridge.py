"""Load the local Logisim engine for generation/testing, without GUI automation."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def start():
    # Java 8 + JPype needs an ASCII path for its native library and class loader.
    vendor = Path(tempfile.gettempdir())/'snake-cpu-tools'
    if not (vendor/'jpype').exists():
        shutil.copytree(ROOT/'tools/_vendor', vendor, dirs_exist_ok=True)
    sys.path.insert(0, str(vendor))
    shutil.copy2(ROOT/'runtime/logisim.exe', vendor/'logisim.jar')
    import jpype as J
    java_home = os.environ.get('SNAKE_JAVA_HOME', r'D:\java')
    jvm = Path(java_home)/'bin/server/jvm.dll'
    J.startJVM(str(jvm), '-Djava.awt.headless=true', classpath=[str(vendor/'logisim.jar')])
    return J


def finish(J, code=0):
    sys.stdout.flush()
    sys.stderr.flush()
    J.java.lang.System.exit(code)
