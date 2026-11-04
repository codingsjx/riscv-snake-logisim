"""Verify user-facing controls through the actual presentation circuit."""
from java_bridge import start,finish,ROOT
from panel_runtime import display_pixels


def check(J):
    loader=J.JClass('com.cburch.logisim.file.Loader')(None)
    f=loader.openLogisimFile(J.java.io.File(str(ROOT/'snake.circ')))
    p=J.JClass('com.cburch.logisim.proj.Project')(f);c=f.getCircuit('Snake')
    s=J.JClass('com.cburch.logisim.circuit.CircuitState')(p,c)
    prop=s.getPropagator();prop.propagate()
    def label(comp):
        return next((str(comp.getAttributeSet().getValue(a)) for a in comp.getAttributeSet().getAttributes() if str(a.getName())=='label'),'')
    buttons={label(x):x for x in c.getNonWires() if str(x.getFactory().getName())=='Button'}
    pins={label(x):x for x in c.getNonWires() if str(x.getFactory().getName())=='Pin'}
    probes={label(x):x for x in c.getNonWires() if str(x.getFactory().getName())=='Probe'}
    core=next(x for x in c.getNonWires() if str(x.getFactory().getName())=='SnakeCore')
    cs=s.getData(core)
    V=J.JClass('com.cburch.logisim.data.Value');W=J.JClass('com.cburch.logisim.data.BitWidth')
    Singleton=J.JClass('com.cburch.logisim.instance.InstanceDataSingleton')
    Loc=J.JClass('com.cburch.logisim.data.Location')
    def button(name,on):
        b=buttons[name];s.setData(b,Singleton(V.TRUE if on else V.FALSE));s.markComponentAsDirty(b);prop.propagate()
    def pin(prefix,value):
        b=next(v for k,v in pins.items() if k.startswith(prefix));width=int(b.getEnds().get(0).getWidth().getWidth())
        b.getFactory().setValue(s.getInstanceState(b),V.createKnown(W.create(width),value));s.markComponentAsDirty(b);prop.propagate()
    def get(name):
        v=s.getValue(probes[name].getLocation());assert v.isFullyDefined();return int(v.toIntValue())
    def cycles(n):
        for _ in range(n*2):prop.tick();prop.propagate();assert not prop.isOscillating()
    def until(test,limit=4000):
        for _ in range(limit):
            if test():return
            cycles(1)
        raise AssertionError('Expected user-facing state was not reached')
    def click(name):
        old=get('FRAME');button(name,True);button(name,False);until(lambda:get('FRAME')!=old);cycles(100)

    pin('MANUAL',1);button('CPU RESET',True);cycles(5);button('CPU RESET',False)
    until(lambda:get('FRAME')==1)
    assert cs.getValue(Loc.create(2800,160)).toIntValue()==0
    for speed,period in enumerate([8192,4096,2048,1024]):
        pin('SPEED',speed);pin('MANUAL',0)
        assert cs.getValue(Loc.create(2800,160)).toIntValue()==period
        pin('MANUAL',1)
        assert cs.getValue(Loc.create(2800,160)).toIntValue()==0
    print('All four speed settings and exact manual mode verified.',flush=True)
    click('START');assert get('STATUS')==1
    # Held STEP generates one event, even over many main-loop iterations.
    old=get('FRAME');button('STEP',True);until(lambda:get('FRAME')!=old)
    after=get('FRAME');cycles(700);assert get('FRAME')==after
    button('STEP',False);cycles(100)
    print('Short click and held-button behavior verified.',flush=True)
    # A second pulse while the CPU is rendering the previous frame must survive.
    old=get('FRAME');button('STEP',True);button('STEP',False)
    until(lambda:get('FRAME')!=old)
    button('STEP',True);button('STEP',False)
    until(lambda:get('FRAME')==old+2);cycles(100)
    assert get('SCORE')==0
    click('STEP');assert get('SCORE')==1 and get('LENGTH')==4
    pixels=display_pixels(s,c)
    assert pixels[(8,11)]==(0,1,1)
    assert sum(color==(0,1,0) for color in pixels.values())==3
    assert sum(color==(1,0,0) for color in pixels.values())==1
    print('Busy-CPU click buffering and RGB display after growth verified.',flush=True)
    click('PAUSE');assert get('STATUS')==2
    before=get('FRAME')
    button('STEP',True);button('STEP',False);cycles(800)
    assert get('FRAME')==before and get('STATUS')==2
    click('PAUSE');assert get('STATUS')==1
    click('RESTART');assert get('STATUS')==0 and get('BEST')==1
    print('Pause, resume, and restart user flow verified.',flush=True)


if __name__=='__main__':
    J=start();code=0
    try:check(J)
    except BaseException:
        import traceback;traceback.print_exc();code=1
    finally:finish(J,code)
