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
             'Register','D Flip-Flop','DotMatrix','RGBLed','LED','Button','Text','Hex Digit Display']
    for lib in loader.getBuiltin().getLibraries():
        for name in names:
            tool = lib.getTool(name)
            if tool is not None: factories[name] = tool.getFactory()
    libraries = {name: num for num, group in {
        '0':['Pin','Tunnel','Constant','Bit Extender','Splitter','Probe','Clock'],
        '1':['AND Gate','NOT Gate','OR Gate'], '2':['Multiplexer'],
        '3':['Comparator','Adder'], '4':['Register','D Flip-Flop'],
        '5':['DotMatrix','RGBLed','LED','Button','Hex Digit Display'], '6':['Text']}.items() for name in group}
    location = J.JClass('com.cburch.logisim.data.Location')
    display=loader.loadJarLibrary(J.java.io.File(str(ROOT/'snake-display.jar')),'snakeio.SnakeDisplayLibrary')
    factories['Snake RGB Display']=display.getTool('Snake RGB Display').getFactory()
    libraries['Snake RGB Display']='9'
    E.SubElement(project,'lib',name='9',desc='jar#snake-display.jar#snakeio.SnakeDisplayLibrary')

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

    def small_tunnel(c,end,label):
        x,y,w=end
        comp(c,'Tunnel',x,y,width=w,label=label,facing='east',labelfont='SansSerif plain 1')

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
    key_pin=(2800,100,8); period_pin=(2800,160,32); map_pin=(2800,220,1)
    for end,label in [(key_pin,'KEYS'),(period_pin,'PERIOD'),(map_pin,'MAP')]:
        comp(core,'Pin',*end[:2],width=end[2],output='false',tristate='false',facing='east',label=label)
        tunnel(core,end,'Game.'+label)
    # Capture button rising edges even while the CPU is busy or not ticking.
    # Software clears only the bits it consumed by writing to 0x70c.
    compare(core,5000,100,0x70c,'Game.AckAddress')
    gate(core,5100,160,'AND Gate',['Game.AckAddress','MemWrite'],'Game.AckWrite')
    raw=comp(core,'Splitter',5000,280,facing='east',fanout=8,incoming=8,appear='center',
             **{f'bit{i}':str(i) for i in range(8)})
    tunnel(core,raw[0],'Game.KEYS')
    ack=comp(core,'Splitter',5200,280,facing='east',fanout=8,incoming=32,appear='center',
             **{f'bit{i}':(str(i) if i<8 else 'none') for i in range(32)})
    tunnel(core,ack[0],'MDin')
    pending=comp(core,'Splitter',5400,280,facing='west',fanout=8,incoming=8,appear='center',
                 **{f'bit{i}':str(i) for i in range(8)})
    tunnel(core,pending[0],'Game.PendingKeys')
    for i in range(8):
        tunnel(core,raw[i+1],f'Game.RawKey.{i}')
        tunnel(core,ack[i+1],f'Game.AckBit.{i}')
        tunnel(core,pending[i+1],f'Game.Pending.{i}')
        y=500+i*160
        gate(core,5100,y,'AND Gate',[f'Game.AckBit.{i}','Game.AckWrite'],f'Game.ClearKey.{i}')
        gate(core,5200,y+60,'OR Gate',[f'Game.ClearKey.{i}','Game.Reset'],f'Game.ResetKey.{i}')
        e=comp(core,'D Flip-Flop',5400,y,trigger='rising',enable='false')
        const(core,e[0],1);tunnel(core,e[1],f'Game.Pending.{i}')
        tunnel(core,e[3],f'Game.ResetKey.{i}');const(core,e[4],0);tunnel(core,e[5],f'Game.RawKey.{i}')
    e=comp(core,'Bit Extender',2920,100,in_width=8,out_width=32,type='zero')
    tunnel(core,e[0],'Game.Keys32');tunnel(core,e[1],'Game.PendingKeys')
    e=comp(core,'Bit Extender',2920,220,in_width=1,out_width=32,type='zero')
    tunnel(core,e[0],'Game.Map32');tunnel(core,e[1],'Game.MAP')
    # Free running 32-bit cycle counter, clocked by the real CPU clock.
    e=comp(core,'Register',3100,180,width=32,trigger='rising',Select='low',label='CPU cycles')
    tunnel(core,e[0],'Game.Tick');tunnel(core,e[1],'Game.TickNext')
    tunnel(core,e[2],'CLK');tunnel(core,e[3],'Game.Reset');const(core,e[4],1)
    e=comp(core,'Adder',3040,280,width=32)
    tunnel(core,e[0],'Game.Tick');const(core,e[1],1);const(core,e[3],0);tunnel(core,e[2],'Game.TickNext')

    # Every mapped register participates in the read mux, enabling framebuffer RMW.
    reads=[(0x700,'Game.Keys32'),(0x704,'Game.Tick'),(0x708,'Game.PERIOD'),(0x710,'Game.Map32')]
    outputs=[]
    reg_specs=[(0x740+4*i,f'ROW{i:02d}') for i in range(16)]
    reg_specs += [(0x780,'SCORE'),(0x784,'STATUS'),(0x788,'HEAD'),(0x78c,'FOOD'),
                  (0x790,'LENGTH'),(0x794,'BEST'),(0x798,'FRAME')]
    reg_specs += [(0x79c,'MODE')]+[(0x7a0+4*i,f'OBS{i:02d}') for i in range(16)]+[(0x7e0,'CAUSE')]
    for i,(addr,name) in enumerate(reg_specs):
        if i<23:x,y=3100+(i//12)*600,440+(i%12)*150
        else:
            j=i-23;x,y=3200+(j//12)*700,3000+(j%12)*150
        sel=f'Game.Select.{name}';enabled=f'Game.Write.{name}';value=f'Game.Out.{name}'
        compare(core,x-200,y,addr,sel)
        gate(core,x-100,y+60,'AND Gate',[sel,'MemWrite'],enabled)
        e=comp(core,'Register',x,y,width=32,trigger='rising',Select='low',label=name)
        tunnel(core,e[0],value);tunnel(core,e[1],'MDin')
        tunnel(core,e[2],'CLK');tunnel(core,e[3],'Game.Reset');tunnel(core,e[4],enabled)
        reads.append((addr,value))
        # Staging registers remain readable. Display banks update only on commit.
        if name!='FRAME':
            d=comp(core,'Register',x+240,y,width=32,trigger='rising',Select='low',label='Display '+name)
            tunnel(core,d[0],'Game.Display.'+name);tunnel(core,d[1],value)
            tunnel(core,d[2],'CLK');tunnel(core,d[3],'Game.Reset');tunnel(core,d[4],'Game.Write.FRAME')
        if name.startswith('ROW'):
            comp(core,'Probe',x+120,y,facing='west',label=name)
            tunnel(core,(x+120,y,32),value)
        elif name in ('SCORE','STATUS','LENGTH','BEST','FRAME','MODE','CAUSE'):
            pin=(x+360,y,32)
            comp(core,'Pin',pin[0],pin[1],width=32,output='true',facing='west',label=name)
            tunnel(core,pin,value if name=='FRAME' else 'Game.Display.'+name)
            outputs.append((name,pin))

    # Two 24-bit buses per row: the Logisim engine limits a value to 32 bits.
    rgb_outputs=[]
    for row in range(16):
        x,y=6000+row*700,320
        bits=comp(core,'Splitter',x,y,facing='east',fanout=16,incoming=32,appear='center',
                  **{f'bit{i}':(str(15-i) if i<16 else 'none') for i in range(32)})
        tunnel(core,bits[0],f'Game.Display.ROW{row:02d}')
        obstacles=comp(core,'Splitter',x+100,y,facing='east',fanout=16,incoming=32,appear='center',
                       **{f'bit{i}':(str(15-i) if i<16 else 'none') for i in range(32)})
        tunnel(core,obstacles[0],f'Game.Display.OBS{row:02d}')
        packed=[comp(core,'Splitter',x+500,y+group*120,facing='west',fanout=8,incoming=24,appear='center',
                     **{f'bit{i}':str(i//3) for i in range(24)}) for group in range(2)]
        for col in range(16):
            tag=f'{row}.{col}';py=550+col*220
            tunnel(core,bits[col+1],'Pixel.Occ.'+tag)
            tunnel(core,obstacles[col+1],'Pixel.Obstacle.'+tag)
            for offset,kind in [(0,'HEAD'),(180,'FOOD')]:
                e=comp(core,'Comparator',x+offset,py,width=32,mode='unsigned')
                tunnel(core,e[0],'Game.Display.'+kind);const(core,e[1],row*16+col)
                tunnel(core,e[3],'Pixel.'+kind+'.'+tag)
            gate(core,x+340,py,'AND Gate',['Pixel.Occ.'+tag,'Pixel.FOOD.'+tag],'Pixel.FoodR.'+tag)
            gate(core,x+420,py,'OR Gate',['Pixel.FoodR.'+tag,'Pixel.Obstacle.'+tag],'Pixel.R.'+tag)
            e=comp(core,'NOT Gate',x+340,py+40,width=1,size=20,facing='east')
            tunnel(core,e[1],'Pixel.FOOD.'+tag);tunnel(core,e[0],'Pixel.NotFood.'+tag)
            gate(core,x+340,py+80,'AND Gate',['Pixel.Occ.'+tag,'Pixel.NotFood.'+tag],'Pixel.G.'+tag)
            gate(core,x+340,py+120,'AND Gate',['Pixel.Occ.'+tag,'Pixel.HEAD.'+tag],'Pixel.HeadB.'+tag)
            gate(core,x+420,py+120,'OR Gate',['Pixel.HeadB.'+tag,'Pixel.Obstacle.'+tag],'Pixel.B.'+tag)
            rgb=comp(core,'Splitter',x+500,py,facing='west',fanout=3,incoming=3,appear='center',
                     bit0='0',bit1='1',bit2='2')
            for i,channel in enumerate('RGB'):tunnel(core,rgb[i+1],'Pixel.'+channel+'.'+tag)
            tunnel(core,rgb[0],'Pixel.RGB.'+tag);tunnel(core,packed[col//8][col%8+1],'Pixel.RGB.'+tag)
        for group in range(2):
            pin=(x+560,y+group*120,24);name=f'RGB{row:02d}{"AB"[group]}'
            comp(core,'Pin',pin[0],pin[1],width=24,output='true',facing='west',label=name)
            wire(core,packed[group][0],pin);rgb_outputs.append((name,pin))
    outputs=rgb_outputs+outputs
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
    E.SubElement(appear,'rect',x='60',y='90',width='340',height='700',fill='#eef5ff',stroke='#21466d',**{'stroke-width':'2'})
    for y,line in [(250,'RISC-V'),(270,'5-stage CPU'),(290,'Snake program')]:
        E.SubElement(appear,'text',x='220',y=str(y),**{'font-size':'16','text-anchor':'middle'}).text=line
    def port(pin,x,y,label,out=False):
        E.SubElement(appear,'circ-port',pin=f'{pin[0]},{pin[1]}',x=str(x-(5 if out else 4)),y=str(y-(5 if out else 4)),width=str(10 if out else 8),height=str(10 if out else 8))
        E.SubElement(appear,'text',x=str(x-8 if out else x+8),y=str(y-5),**{'font-size':'9','text-anchor':'end' if out else 'start'}).text=label
    port(key_pin,60,140,'KEYS');port(period_pin,60,200,'PERIOD');port((50,50,1),60,340,'RESET')
    port(map_pin,60,400,'MAP')
    positions={}
    for i,(name,pin) in enumerate(outputs):
        y=100+i*10 if i<32 else 460+(i-32)*50
        port(pin,400,y,name,True);positions[name]=(640,350+y-100,pin[2])
    E.SubElement(appear,'circ-anchor',x='197',y='97',width='6',height='6',facing='east')

    # A clean presentation circuit above the existing CPU circuit list.
    main=E.Element('circuit',name='Snake')
    E.SubElement(main,'a',name='circuit',val='Snake')
    E.SubElement(main,'comp',name='SnakeCore',loc='(440,350)')
    project.insert(list(project).index(project.findall('circuit')[0]),main)
    project.find('main').set('name','Snake')
    text(main,80,65,'自制 RISC-V 贪吃蛇 | CPU + 汇编程序 + 彩色显示',22)
    text(main,80,95,'短按会被锁存；开启仿真时钟后，CPU 自动读取按键事件。',14)
    text(main,80,125,'MANUAL=1 手动单步；MANUAL=0 自动移动。SPEED=0/1/2/3 从慢到快。',12)
    text(main,80,155,'青色：蛇头    绿色：蛇身    红色：食物    紫色：障碍物',12)
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
    wire(main,e[0],(260,710));tunnel(main,(260,710,1),'Manual')
    e=comp(main,'Pin',200,770,width=2,output='false',tristate='false',facing='east',label='SPEED 0/1/2/3')
    wire(main,e[0],(260,770));tunnel(main,(260,770,2),'Speed')
    e=comp(main,'Pin',200,930,width=1,output='false',tristate='false',facing='east',label='OBSTACLES 0/1')
    wire(main,e[0],(260,930));tunnel(main,(260,930,1),'Map');tunnel(main,(300,650,1),'Map')
    e=comp(main,'Multiplexer',250,850,width=32,select=2,enable='false',selloc='tr',facing='east')
    for end,value in zip(e[:4],[8192,4096,2048,1024]):const(main,end,value)
    tunnel(main,e[4],'Speed');tunnel(main,e[5],'AutoPeriod')
    e=comp(main,'Multiplexer',250,450,width=32,select=1,enable='false',selloc='tr',facing='east')
    tunnel(main,e[0],'AutoPeriod');const(main,e[1],0);tunnel(main,e[2],'Manual');wire(main,e[3],(300,450))
    e=comp(main,'Button',230,590,facing='east',label='CPU RESET',labelloc='west',color='#ff8888')
    wire(main,e[0],(300,590))
    display=comp(main,'Snake RGB Display',1000,350)
    for row in range(16):
        for group in range(2):
            end=positions[f'RGB{row:02d}{"AB"[group]}']
            wire(main,end,display[row*2+group])
    # Readable decimal probes avoid forcing viewers to interpret hexadecimal scores.
    for i,name in enumerate(['SCORE','STATUS','LENGTH','BEST','FRAME','MODE','CAUSE']):
        out=positions[name]
        y=out[1]
        wire(main,out,(780,y))
        e=comp(main,'Probe',780,y,facing='west',radix='10unsigned',label=name,labelloc='north')
    text(main,1000,730,'状态：0 准备 / 1 运行 / 2 暂停 / 3 结束 / 4 获胜',13)
    text(main,1000,765,'START 开始；PAUSE 暂停/恢复。',13)
    text(main,1000,795,'RESTART 重开并保留最高分。',13)
    text(main,1000,835,'SPEED：0 慢 / 1 中 / 2 快 / 3 很快',13)
    text(main,1000,875,'OBSTACLES=0 经典；=1 障碍地图；切换后按 RESTART 生效。',12)
    text(main,1000,915,'CAUSE：0 无碰撞 / 1 撞墙 / 2 撞蛇身 / 3 撞障碍',12)
    E.indent(tree,space='  ')
    (ROOT/'snake.circ').write_bytes(E.tostring(project,encoding='UTF-8',xml_declaration=True))
    (ROOT/'build/symbols.json').write_text(json.dumps(labels,indent=2),encoding='utf-8')
    print(f'Built snake.circ: {len(words)} ROM words, original CPU circuits retained.')


if __name__=='__main__':
    J=start();code=0
    try:generate(J)
    except BaseException:
        import traceback;traceback.print_exc();code=1
    finally:finish(J,code)
