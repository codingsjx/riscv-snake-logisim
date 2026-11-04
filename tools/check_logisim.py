"""Execute the real supplied forwarding CPU through the Logisim engine."""
import sys
from java_bridge import start, finish, ROOT


def check(J):
    loader=J.JClass('com.cburch.logisim.file.Loader')(None)
    file=loader.openLogisimFile(J.java.io.File(str(ROOT/'snake.circ')))
    project=J.JClass('com.cburch.logisim.proj.Project')(file)
    core=file.getCircuit('SnakeCore')
    state=J.JClass('com.cburch.logisim.circuit.CircuitState')(project,core)
    prop=state.getPropagator()
    pins={}
    for c in core.getNonWires():
        if str(c.getFactory().getName())=='Pin':
            label=next((str(c.getAttributeSet().getValue(a)) for a in c.getAttributeSet().getAttributes() if str(a.getName())=='label'),'')
            pins[label]=c
    Width=J.JClass('com.cburch.logisim.data.BitWidth')
    Value=J.JClass('com.cburch.logisim.data.Value')

    def set_pin(label,value):
        c=pins[label];instance=state.getInstanceState(c)
        width=int(c.getEnds().get(0).getWidth().getWidth())
        c.getFactory().setValue(instance,Value.createKnown(Width.create(width),value))
        state.markComponentAsDirty(c);prop.propagate()

    def get(label):
        v=state.getValue(pins[label].getLocation())
        if not v.isFullyDefined(): raise AssertionError(f'{label} is {v}')
        return int(v.toIntValue()) & 0xffffffff

    def run(cycles):
        for _ in range(cycles*2):
            prop.tick();prop.propagate()
            if prop.isOscillating():raise AssertionError('circuit oscillation')

    def wait(predicate,limit=4000):
        for i in range(limit):
            if predicate():return i
            run(1)
        dump={k:str(state.getValue(v.getLocation())) for k,v in pins.items()}
        raise AssertionError(f'CPU did not reach expected state: {dump}')

    def press(keys):
        old=get('FRAME');set_pin('KEYS',keys)
        wait(lambda:get('FRAME')!=old)
        set_pin('KEYS',0);run(100)

    set_pin('KEYS',0);set_pin('PERIOD',0x7fffffff);set_pin('RESET',1)
    run(5);set_pin('RESET',0)
    elapsed=wait(lambda:get('FRAME')>=1)
    print('INITIAL',elapsed,'cycles', {k:get(k) for k in ['STATUS','SCORE','LENGTH','ROW08','FRAME']},flush=True)
    assert get('STATUS')==0 and get('LENGTH')==3 and get('ROW08')==0x0710
    press(16)
    assert get('STATUS')==1
    print('START passed',flush=True)
    press(128)
    assert get('ROW08')==0x0390
    print('MOVE passed',flush=True)
    press(32);assert get('STATUS')==2
    press(32);assert get('STATUS')==1
    print('PAUSE / RESUME passed',flush=True)
    for _ in range(3):press(128)
    assert get('SCORE')==1 and get('LENGTH')==4 and get('BEST')==1
    print('EAT / GROW / SCORE passed',flush=True)
    press(64)
    assert get('STATUS')==0 and get('SCORE')==0 and get('BEST')==1 and get('ROW08')==0x0710
    print('RESTART passed. Actual Logisim forwarding CPU checks complete.',flush=True)


if __name__=='__main__':
    J=start();code=0
    try:check(J)
    except BaseException:
        import traceback;traceback.print_exc();code=1
    finally:finish(J,code)
