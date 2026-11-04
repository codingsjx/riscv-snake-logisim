"""Create a separate game project from the user's original circuit.

All new component port positions are taken from the actual installed Logisim
engine, rather than inferred from drawing dimensions.
"""
import copy
import json
import xml.etree.ElementTree as E
from pathlib import Path
from rv32 import build
from java_bridge import start, finish, ROOT


def point(x, y): return f'({x},{y})'


def generate(J):
    words, labels = build(ROOT)
    tree = E.parse(ROOT/'original/cpu21-riscv.circ')
    project = tree.getroot()
    # Use an ASCII-named reference in the directory containing the supplied jars.
    loader = J.JClass('com.cburch.logisim.file.Loader')(None)
    reference = loader.openLogisimFile(J.java.io.File(str(ROOT/'cpu_reference.circ')))
    factories = {}
    names = ['Pin','Tunnel','Constant','Bit Extender','Splitter','Probe','Clock',
             'AND Gate','NOT Gate','OR Gate','Multiplexer','Comparator','Adder',
             'Register','DotMatrix','Button','Text','Hex Digit Display']
    for lib in loader.getBuiltin().getLibraries():
        for name in names:
            tool = lib.getTool(name)
            if tool is not None: factories[name] = tool.getFactory()
    libraries = {name: num for num, group in {
        '0':['Pin','Tunnel','Constant','Bit Extender','Splitter','Probe','Clock'],
        '1':['AND Gate','NOT Gate','OR Gate'], '2':['Multiplexer'],
        '3':['Comparator','Adder'], '4':['Register'],
        '5':['DotMatrix','Button','Hex Digit Display'], '6':['Text']}.items() for name in group}
    location = J.JClass('com.cburch.logisim.data.Location')

    def comp(c, name, x, y, **attrs):
        el = E.SubElement(c, 'comp', lib=libraries[name], loc=point(x,y), name=name)
        for k,v in attrs.items(): E.SubElement(el,'a',name=k,val=str(v))
        factory = factories[name]
        aset = factory.createAttributeSet()
        for key, val in attrs.items():
            attr = next((a for a in list(aset.getAttributes()) if str(a.getName()) == key), None)
            if attr is None: raise ValueError(f'{name}: unknown attribute {key}')
            aset.setValue(attr, attr.parse(str(val)))
        obj = factory.createComponent(location.create(x,y), aset)
        return [(int(e.getLocation().getX()),int(e.getLocation().getY()),int(e.getWidth().getWidth())) for e in obj.getEnds()]

    def tunnel(c, end, label):
        x,y,w = end
        comp(c,'Tunnel',x,y,width=w,label=label,facing='east')

    def const(c, end, value):
        x,y,w = end
        comp(c,'Constant',x,y,width=w,value=hex(value & ((1<<w)-1)),facing='east')

    def text(c,x,y,value,size=14):
        comp(c,'Text',x,y,text=value,font=f'SansSerif plain {size}',halign='left')

    def wire(c,p,q):
        E.SubElement(c,'wire',{'from':point(*p[:2]),'to':point(*q[:2])})

    def compare(c,x,y,address,label):
        e=comp(c,'Comparator',x,y,width=32,mode='unsigned')
        tunnel(c,e[0],'MEM.AluResult'); const(c,e[1],address); tunnel(c,e[3],label)

    def gate(c,x,y,name,inputs,out):
        e=comp(c,name,x,y,width=1,inputs=2,size=30,facing='east')
        for end,label in zip(e[1:],inputs):tunnel(c,end,label)
        tunnel(c,e[0],out)

    # Retain all existing CPU versions; add a derived forwarding core.
    core=copy.deepcopy(project.findall('circuit')[8]);core.set('name','SnakeCore')
    core.find("a[@name='circuit']").set('val','SnakeCore')
    project.append(core)
    for el in core.findall('comp'):
        if el.get('name')=='Pin':
            # Original monitor outputs become probes; interrupt inputs are tied low.
            attrs={a.get('name'):a.get('val') for a in el.findall('a')}
            if attrs.get('output')=='true':
                el.set('name','Probe')
            else:
                el.set('name','Constant')
                for a in list(el): el.remove(a)
                E.SubElement(el,'a',name='width',val=attrs.get('width','1'))
                E.SubElement(el,'a',name='value',val='0x0')
        if el.get('name')=='Button' and el.get('loc')=='(50,50)':
            el.set('name','Pin');el.set('lib','0')
            for a in list(el):el.remove(a)
            for k,v in {'facing':'east','output':'false','width':'1','tristate':'false','label':'RESET'}.items():E.SubElement(el,'a',name=k,val=v)
            tunnel(core,(50,50,1),'Game.Reset')
        if el.get('name')=='Tunnel' and el.get('loc')=='(1610,1010)':
            el.find("a[@name='label']").set('val','Game.RamWrite')
        if el.get('name')=='ROM':
            el.find("a[@name='contents']").text='addr/data: 10 32\n'+'\n'.join(f'{w:08x}' for w in words)+'\n'
    # Intercept the raw RAM output, preserving the existing load/writeback path.
    target={'(1720,930)','(1850,930)'}
    for w in list(core.findall('wire')):
        if {w.get('from'),w.get('to')}==target:core.remove(w)
    tunnel(core,(1720,930,32),'Game.RamData')
    tunnel(core,(1850,930,32),'Game.ReadData')

    # New externally visible pins; keep them away from existing datapath wires.
    key_pin=(2800,100,8); period_pin=(2800,160,32)
    for end,label in [(key_pin,'KEYS'),(period_pin,'PERIOD')]:
        comp(core,'Pin',*end[:2],width=end[2],output='false',tristate='false',facing='east',label=label)
        tunnel(core,end,'Game.'+label)
    e=comp(core,'Bit Extender',2920,100,in_width=8,out_width=32,type='zero')
    tunnel(core,e[0],'Game.Keys32');tunnel(core,e[1],'Game.KEYS')
    # Free running 32-bit cycle counter, clocked by the real CPU clock.
    e=comp(core,'Register',3100,180,width=32,trigger='rising',Select='low',label='CPU cycles')
    tunnel(core,e[0],'Game.Tick');tunnel(core,e[1],'Game.TickNext')
    tunnel(core,e[2],'CLK');tunnel(core,e[3],'Game.Reset');const(core,e[4],1)
    e=comp(core,'Adder',3040,280,width=32)
    tunnel(core,e[0],'Game.Tick');const(core,e[1],1);const(core,e[3],0);tunnel(core,e[2],'Game.TickNext')

    # Every mapped register participates in the read mux, enabling framebuffer RMW.
    reads=[(0x700,'Game.Keys32'),(0x704,'Game.Tick'),(0x708,'Game.PERIOD')]
    outputs=[]
    reg_specs=[(0x740+4*i,f'ROW{i:02d}') for i in range(16)]
    reg_specs += [(0x780,'SCORE'),(0x784,'STATUS'),(0x788,'HEAD'),(0x78c,'FOOD'),
                  (0x790,'LENGTH'),(0x794,'BEST'),(0x798,'FRAME')]
    for i,(addr,name) in enumerate(reg_specs):
        x,y=3100+(i//12)*600,440+(i%12)*150
        sel=f'Game.Select.{name}';enabled=f'Game.Write.{name}';value=f'Game.Out.{name}'
        compare(core,x-200,y,addr,sel)
        gate(core,x-100,y+60,'AND Gate',[sel,'MemWrite'],enabled)
        e=comp(core,'Register',x,y,width=32,trigger='rising',Select='low',label=name)
        tunnel(core,e[0],value);tunnel(core,e[1],'MDin')
        tunnel(core,e[2],'CLK');tunnel(core,e[3],'Game.Reset');tunnel(core,e[4],enabled)
        reads.append((addr,value))
        if name.startswith('ROW') or name in ('SCORE','STATUS','LENGTH','BEST','FRAME'):
            pin=(x+120,y,32)
            comp(core,'Pin',pin[0],pin[1],width=32,output='true',facing='west',label=name)
            tunnel(core,pin,value);outputs.append((name,pin))
    # Reserve the entire 0x700..0x7ff page. Avoid duplicate writes to data RAM.
    e=comp(core,'Splitter',4400,100,facing='east',fanout=1,incoming=32,appear='center',
           **{f'bit{i}':('none' if i<8 else '0') for i in range(32)})
    tunnel(core,e[0],'MEM.AluResult');tunnel(core,e[1],'Game.AddressPage')
    e=comp(core,'Comparator',4520,100,width=24,mode='unsigned')
    tunnel(core,e[0],'Game.AddressPage');const(core,e[1],7);tunnel(core,e[3],'Game.IsIO')
    e=comp(core,'NOT Gate',4600,100,width=1,size=20,facing='east')
    tunnel(core,e[1],'Game.IsIO');tunnel(core,e[0],'Game.NotIO')
    gate(core,4700,160,'AND Gate',['Game.NotIO','MemWrite'],'Game.RamWrite')
    prev='Game.Zero'
    comp(core,'Constant',4400,250,width=32,value='0x0');tunnel(core,(4400,250,32),prev)
    for i,(addr,value) in enumerate(reads):
        x,y=4500,350+i*100
        sel=f'Game.ReadSel.{i}';out=f'Game.Mux.{i}'
        compare(core,x-100,y,addr,sel)
        e=comp(core,'Multiplexer',x,y,width=32,select=1,enable='false',selloc='tr',facing='east')
        tunnel(core,e[0],prev);tunnel(core,e[1],value);tunnel(core,e[2],sel);tunnel(core,e[3],out)
        prev=out
    e=comp(core,'Multiplexer',4800,300,width=32,select=1,enable='false',selloc='tr',facing='east')
    tunnel(core,e[0],'Game.RamData');tunnel(core,e[1],prev);tunnel(core,e[2],'Game.IsIO');tunnel(core,e[3],'Game.ReadData')

    # Compact external appearance; internal CPU drawing remains accessible.
    appear=E.SubElement(core,'appear')
    E.SubElement(appear,'rect',x='60',y='90',width='340',height='440',fill='#eef5ff',stroke='#21466d',**{'stroke-width':'2'})
    for y,line in [(250,'RISC-V'),(270,'5-stage CPU'),(290,'Snake program')]:
        E.SubElement(appear,'text',x='220',y=str(y),**{'font-size':'16','text-anchor':'middle'}).text=line
    def port(pin,x,y,label,out=False):
        E.SubElement(appear,'circ-port',pin=f'{pin[0]},{pin[1]}',x=str(x-(5 if out else 4)),y=str(y-(5 if out else 4)),width=str(10 if out else 8),height=str(10 if out else 8))
        E.SubElement(appear,'text',x=str(x-8 if out else x+8),y=str(y-5),**{'font-size':'9','text-anchor':'end' if out else 'start'}).text=label
    port(key_pin,60,140,'KEYS');port(period_pin,60,200,'PERIOD');port((50,50,1),60,340,'RESET')
    positions={}
    for i,(name,pin) in enumerate(outputs):
        y=100+i*10 if i<16 else 300+(i-16)*50
        port(pin,400,y,name,True);positions[name]=(640,350+y-100,32)
    E.SubElement(appear,'circ-anchor',x='197',y='97',width='6',height='6',facing='east')

    # A clean presentation circuit above the existing CPU circuit list.
    main=E.Element('circuit',name='Snake')
    E.SubElement(main,'a',name='circuit',val='Snake')
    E.SubElement(main,'comp',name='SnakeCore',loc='(440,350)')
    project.insert(list(project).index(project.findall('circuit')[0]),main)
    project.find('main').set('name','Snake')
    text(main,80,65,'RISC-V SNAKE | CPU + PROGRAM + I/O',22)
    text(main,80,95,'Start -> steer -> eat -> score. Pause / restart supported.',14)
    text(main,80,125,'Enable simulation ticks. Hold buttons until the CPU polls them.',12)
    text(main,80,155,'MANUAL=1: use STEP. MANUAL=0: automatic movement.',12)
    key_positions=[]
    for i,name in enumerate(['UP','RIGHT','DOWN','LEFT','START','PAUSE','RESTART','STEP']):
        x,y=110,240+i*55
        e=comp(main,'Button',x,y,facing='east',label=name,labelloc='west',color='#66ccff')
        wire(main,e[0],(180,y));tunnel(main,(180,y,1),f'K{i}');key_positions.append(e[0])
    e=comp(main,'Splitter',220,390,facing='west',fanout=8,incoming=8,appear='center',**{f'bit{i}':str(i) for i in range(8)})
    tunnel(main,e[0],'Keys')
    for i,end in enumerate(e[1:]):
        comp(main,'Tunnel',end[0],end[1],width=1,label=f'K{i}',facing='east',labelfont='SansSerif plain 8')
    tunnel(main,(300,390,8),'Keys')
    # Default manual mode = 0, i.e. automatic. Users may toggle this input pin.
    e=comp(main,'Pin',200,710,width=1,output='false',tristate='false',facing='east',label='MANUAL (click 0/1)')
    tunnel(main,e[0],'Manual')
    e=comp(main,'Multiplexer',250,450,width=32,select=1,enable='false',selloc='tr',facing='east')
    const(main,e[0],4096);const(main,e[1],0x7fffffff);tunnel(main,e[2],'Manual');wire(main,e[3],(300,450))
    e=comp(main,'Button',230,590,facing='east',label='CPU RESET',labelloc='west',color='#ff8888')
    wire(main,e[0],(300,590))
    matrix=comp(main,'DotMatrix',1000,350,inputtype='row',matrixcols=16,matrixrows=16,
                color='#36d981',offcolor='#18282c',persist=0,dotshape='square')
    text(main,950,295,'16 x 16 GAME BOARD',16)
    for i in range(16):
        end=positions[f'ROW{i:02d}'];x,y,_=end
        e=comp(main,'Splitter',740,y,facing='east',fanout=1,incoming=32,appear='center',
               **{f'bit{j}':('0' if j<16 else 'none') for j in range(32)})
        wire(main,end,e[0]);wire(main,e[1],matrix[i])
    # Readable decimal probes avoid forcing viewers to interpret hexadecimal scores.
    for i,name in enumerate(['SCORE','STATUS','LENGTH','BEST','FRAME']):
        out=positions[name]
        y=out[1]
        wire(main,out,(1000,y))
        e=comp(main,'Probe',1000,y,facing='west',radix='10unsigned',label=name,labelloc='north')
    text(main,760,815,'STATUS: 0 READY / 1 RUN / 2 PAUSE / 3 GAME OVER / 4 WIN',12)
    text(main,760,840,'Snake = connected cells; food = isolated cell. First food is ahead.',12)
    tree.write(ROOT/'snake.circ',encoding='UTF-8',xml_declaration=True)
    (ROOT/'build/symbols.json').write_text(json.dumps(labels,indent=2),encoding='utf-8')
    print(f'Built snake.circ: {len(words)} ROM words, original CPU circuits retained.')


if __name__=='__main__':
    J=start();code=0
    try:generate(J)
    except BaseException:
        import traceback;traceback.print_exc();code=1
    finally:finish(J,code)
