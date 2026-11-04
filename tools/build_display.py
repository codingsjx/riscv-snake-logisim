"""Compile the small open-source output peripheral using Java 8 and Eclipse ECJ."""
import os
from pathlib import Path
import subprocess
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def build_display():
    compiler=ROOT/'tools/_vendor/ecj-4.6.1.jar'
    if not compiler.exists():
        compiler.parent.mkdir(parents=True,exist_ok=True)
        urllib.request.urlretrieve('https://repo.maven.apache.org/maven2/org/eclipse/jdt/core/compiler/ecj/4.6.1/ecj-4.6.1.jar',compiler)
    dest=ROOT/'build/display-classes';dest.mkdir(parents=True,exist_ok=True)
    java=Path(os.environ.get('SNAKE_JAVA_HOME',r'D:\java'))/'bin/java.exe'
    subprocess.run([str(java),'-jar',str(compiler),'-1.8','-encoding','UTF-8','-cp',
                    str(ROOT/'runtime/logisim.exe'),'-d',str(dest),
                    *[str(p) for p in sorted((ROOT/'display').glob('*.java'))]],check=True)
    with zipfile.ZipFile(ROOT/'snake-display.jar','w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(dest.rglob('*.class')):z.write(p,p.relative_to(dest).as_posix())
    print('Built snake-display.jar from display/*.java')


if __name__=='__main__':build_display()
