"""Verify responsive and unresponsive single-instance paths in real processes."""
import os
import subprocess
import sys
import uuid
from PySide6.QtCore import QCoreApplication
from config import ROOT
from instance import activate_existing


def server(name,healthy):
    code='''
import sys
from PySide6.QtCore import QCoreApplication,QTimer
from PySide6.QtNetwork import QLocalServer
from instance import attach_activation
app=QCoreApplication([])
s=QLocalServer();assert s.listen(sys.argv[1]),s.errorString()
def activated():
    print('activated',flush=True)
    QTimer.singleShot(100,app.quit)
if sys.argv[2]=='yes':attach_activation(s,activated)
QTimer.singleShot(8000,app.quit)
print('ready',flush=True)
app.exec()
'''
    child=subprocess.Popen([sys.executable,'-c',code,name,'yes' if healthy else 'no'],cwd=ROOT,
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    assert child.stdout.readline().strip()=='ready'
    return child


def main():
    app=QCoreApplication([])
    name='robin-test-'+uuid.uuid4().hex
    assert not activate_existing(name,timeout=100)
    child=server(name,True)
    try:
        assert activate_existing(name,timeout=1000)
        assert child.stdout.readline().strip()=='activated'
        assert child.wait(timeout=5)==0
    finally:
        if child.poll() is None:child.terminate();child.wait(timeout=5)
    name='robin-test-'+uuid.uuid4().hex
    child=server(name,False)
    try:
        try:activate_existing(name,timeout=150)
        except RuntimeError:pass
        else:raise AssertionError('Connected but unresponsive pipe must not count as successful startup')
    finally:
        child.terminate();child.wait(timeout=5)
    print('PASS: fresh launch; acknowledged activation in another process; unresponsive pipe reports failure instead of silently exiting')


if __name__=='__main__':main()
