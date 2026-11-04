"""Render the actual Logisim presentation circuit to a PNG, headlessly."""
from java_bridge import start, finish, ROOT


def render(J):
    loader=J.JClass('com.cburch.logisim.file.Loader')(None)
    file=loader.openLogisimFile(J.java.io.File(str(ROOT/'snake.circ')))
    project=J.JClass('com.cburch.logisim.proj.Project')(file)
    circuit=file.getCircuit('Snake')
    state=J.JClass('com.cburch.logisim.circuit.CircuitState')(project,circuit)
    prop=state.getPropagator();prop.propagate()
    core=next(c for c in circuit.getNonWires() if str(c.getFactory().getName())=='SnakeCore')
    core_state=state.getData(core)
    Location=J.JClass('com.cburch.logisim.data.Location')
    Value=J.JClass('com.cburch.logisim.data.Value')
    Singleton=J.JClass('com.cburch.logisim.instance.InstanceDataSingleton')
    def label(c):
        return next((str(c.getAttributeSet().getValue(a)) for a in c.getAttributeSet().getAttributes() if str(a.getName())=='label'),'')
    buttons={label(c):c for c in circuit.getNonWires() if str(c.getFactory().getName())=='Button'}
    for i,name in enumerate(['UP','RIGHT','DOWN','LEFT','START','PAUSE','RESTART','STEP']):
        button=buttons[name]
        state.setData(button,Singleton(Value.TRUE));state.markComponentAsDirty(button);prop.propagate()
        keys=core_state.getValue(Location.create(2800,100))
        assert keys.isFullyDefined() and int(keys.toIntValue())==1<<i,f'{name}={keys}'
        state.setData(button,Singleton(Value.FALSE));state.markComponentAsDirty(button);prop.propagate()
    reset=buttons['CPU RESET']
    state.setData(reset,Singleton(Value.TRUE));state.markComponentAsDirty(reset);prop.propagate()
    assert core_state.getValue(Location.create(50,50))==Value.TRUE
    state.setData(reset,Singleton(Value.FALSE));state.markComponentAsDirty(reset);prop.propagate()
    print('Verified all 8 panel buttons and CPU reset routing.',flush=True)
    for _ in range(1000):prop.tick();prop.propagate()
    matrix=next(c for c in circuit.getNonWires() if str(c.getFactory().getName())=='DotMatrix')
    rows=[state.getValue(e.getLocation()) for e in matrix.getEnds()]
    assert all(v.isFullyDefined() for v in rows),str(rows)
    assert int(rows[8].toIntValue())==0x0710, str(rows)
    for name,expected in [('SCORE',0),('STATUS',0),('LENGTH',3),('BEST',0),('FRAME',1)]:
        probe=next(c for c in circuit.getNonWires() if str(c.getFactory().getName())=='Probe' and any(str(a.getName())=='label' and str(c.getAttributeSet().getValue(a))==name for a in c.getAttributeSet().getAttributes()))
        value=state.getValue(probe.getLocation())
        assert value.isFullyDefined() and int(value.toIntValue())==expected,f'{name}={value}'
    # Inspect the actual matrix's coordinate mapping, not just its bus inputs.
    data=state.getData(matrix)
    field=data.getClass().getDeclaredField('grid');field.setAccessible(True)
    print('ACTIVE PIXELS',[(i//16,i%16) for i,v in enumerate(field.get(data)) if str(v)=='1'],flush=True)
    image=J.JClass('java.awt.image.BufferedImage')(1560,1120,1)
    graphics=image.createGraphics()
    graphics.setColor(J.JClass('java.awt.Color').WHITE);graphics.fillRect(0,0,1560,1120)
    graphics.scale(1.25,1.25)
    context=J.JClass('com.cburch.logisim.comp.ComponentDrawContext')(J.JClass('javax.swing.JPanel')(),circuit,state,graphics,graphics)
    circuit.draw(context,J.java.util.Collections.emptySet())
    J.JClass('javax.imageio.ImageIO').write(image,'png',J.java.io.File(str(ROOT/'build/panel.png')))
    graphics.dispose()
    print('Verified top-level display wiring and rendered build/panel.png')


if __name__=='__main__':
    J=start();code=0
    try:render(J)
    except BaseException:
        import traceback;traceback.print_exc();code=1
    finally:finish(J,code)
