"""Record state-by-state gameplay from the actual Logisim CPU and native display.

The GIF is a presentation of sampled circuit states, not a real-time screen capture.
Game pixels are visualized from Logisim RGB input values; no game logic is reimplemented.
"""
import json
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from java_bridge import start, finish, ROOT
from panel_runtime import pixel_board,display_pixels
from game_map import OBSTACLES


def demonstrate(J,obstacle_mode=False):
    dest=ROOT/('build/obstacle_demo_frames' if obstacle_mode else 'build/demo_frames')
    dest.mkdir(parents=True,exist_ok=True)
    loader=J.JClass('com.cburch.logisim.file.Loader')(None)
    file=loader.openLogisimFile(J.java.io.File(str(ROOT/'snake.circ')))
    project=J.JClass('com.cburch.logisim.proj.Project')(file)
    circuit=file.getCircuit('Snake')
    state=J.JClass('com.cburch.logisim.circuit.CircuitState')(project,circuit)
    prop=state.getPropagator();prop.propagate()
    Value=J.JClass('com.cburch.logisim.data.Value')
    Singleton=J.JClass('com.cburch.logisim.instance.InstanceDataSingleton')

    def label(c):
        return next((str(c.getAttributeSet().getValue(a)) for a in c.getAttributeSet().getAttributes() if str(a.getName())=='label'),'')
    buttons={label(c):c for c in circuit.getNonWires() if str(c.getFactory().getName())=='Button'}
    probes={label(c):c for c in circuit.getNonWires() if str(c.getFactory().getName())=='Probe'}
    manual=next(c for c in circuit.getNonWires() if str(c.getFactory().getName())=='Pin' and label(c).startswith('MANUAL'))
    manual.getFactory().setValue(state.getInstanceState(manual),Value.TRUE)
    state.markComponentAsDirty(manual);prop.propagate()
    if obstacle_mode:
        mode=next(c for c in circuit.getNonWires() if str(c.getFactory().getName())=='Pin' and label(c).startswith('OBSTACLES'))
        mode.getFactory().setValue(state.getInstanceState(mode),Value.TRUE)
        state.markComponentAsDirty(mode);prop.propagate()

    def button(name,down):
        c=buttons[name]
        state.setData(c,Singleton(Value.TRUE if down else Value.FALSE))
        state.markComponentAsDirty(c);prop.propagate()

    def get(name):
        v=state.getValue(probes[name].getLocation())
        assert v.isFullyDefined(),f'{name}={v}'
        return int(v.toIntValue()) & 0xffffffff

    def run(n):
        for _ in range(n*2):
            prop.tick();prop.propagate()
            assert not prop.isOscillating(),'Circuit oscillation'

    def wait(predicate,limit=4000):
        for _ in range(limit):
            if predicate():return
            run(1)
        raise TimeoutError('CPU failed to complete expected frame')

    def press(*names):
        old=get('FRAME')
        for name in names:button(name,True)
        for name in names:button(name,False)
        wait(lambda:get('FRAME')!=old)
        run(100)

    bold=r'C:\Windows\Fonts\msyhbd.ttc'
    regular=r'C:\Windows\Fonts\msyh.ttc'
    def font(size,strong=False):return ImageFont.truetype(bold if strong else regular,size)
    frames=[];durations=[];records=[]
    status_names={0:'准备开始',1:'正在运行',2:'已暂停',3:'游戏结束',4:'获胜'}
    def capture(action,duration=800):
        index=len(frames)
        data={name:get(name) for name in ['SCORE','STATUS','LENGTH','BEST','FRAME','MODE','CAUSE']}
        colors=display_pixels(state,circuit)
        purple={p for p,color in colors.items() if color==(1,0,1)}
        assert purple==({(y,x) for x,y in OBSTACLES} if obstacle_mode else set())
        assert not any(colors[(y,x)]==(1,0,0) for x,y in OBSTACLES) if obstacle_mode else True
        image=J.JClass('java.awt.image.BufferedImage')(1460,1160,1)
        graphics=image.createGraphics()
        graphics.setColor(J.JClass('java.awt.Color').WHITE);graphics.fillRect(0,0,1460,1160)
        context=J.JClass('com.cburch.logisim.comp.ComponentDrawContext')(J.JClass('javax.swing.JPanel')(),circuit,state,graphics,graphics)
        circuit.draw(context,J.java.util.Collections.emptySet())
        native=dest/f'{index:02d}_native.png'
        J.JClass('javax.imageio.ImageIO').write(image,'png',J.java.io.File(str(native)))
        if obstacle_mode and index==0:
            J.JClass('javax.imageio.ImageIO').write(image,'png',J.java.io.File(str(ROOT/'build/obstacles-panel.png')))
        graphics.dispose()
        # Read the actual 256 RGB LED inputs; only presentation scaling is applied.
        board=pixel_board(state,circuit)
        frame=Image.new('RGB',(1240,860),'#101c2a')
        draw=ImageDraw.Draw(frame)
        title='贪吃蛇 · 障碍挑战模式' if obstacle_mode else '贪吃蛇 · 自制 RISC-V CPU 实际运行'
        draw.text((40,23),title,font=font(30,True),fill='#f0f5fb')
        legend='青色蛇头 · 绿色蛇身 · 红色食物 · 紫色障碍物' if obstacle_mode else 'Logisim 重定向流水线  /  青色蛇头 · 绿色蛇身 · 红色食物'
        draw.text((42,69),legend,font=font(17),fill='#a6b8ce')
        frame.paste(board,(42,128))
        draw.rectangle((41,127,682,768),outline='#47627e',width=2)
        x=730
        state_color='#f9b75a' if data['STATUS'] in (0,2) else '#f17a7a' if data['STATUS']==3 else '#45d69d'
        draw.text((x,135),'当前状态',font=font(17),fill='#a6b8ce')
        draw.text((x,165),status_names[data['STATUS']],font=font(32,True),fill=state_color)
        for i,(name,title) in enumerate([('SCORE','当前得分'),('LENGTH','蛇身长度'),('BEST','最高得分')]):
            top=238+i*108
            draw.rounded_rectangle((x,top,1190,top+90),radius=12,fill='#1b2c40')
            draw.text((x+22,top+14),title,font=font(18),fill='#a6b8ce')
            draw.text((x+350,top+12),str(data[name]),font=font(40,True),fill='#f1f6fc')
        draw.text((x,590),'本步操作',font=font(17),fill='#a6b8ce')
        # Keep captions short enough for a single line in the information panel.
        draw.text((x,625),action,font=font(24,True),fill='#77c9ff')
        draw.text((x,689),f"画面更新次数  {data['FRAME']}",font=font(18),fill='#a6b8ce')
        draw.text((42,801),'实际 RGB 显示信号可视化，非实时录屏；播放节奏经过调整。',font=font(18),fill='#a6b8ce')
        frame.save(dest/f'{index:02d}_demo.png')
        frames.append(frame);durations.append(duration)
        records.append({'step':index,'action':action,'cpu_cycles':int(prop.getTickCount())//2,**data})
        print('FRAME',index,action,data,flush=True)

    button('CPU RESET',True);run(5);button('CPU RESET',False)
    wait(lambda:get('FRAME')==1)
    assert get('LENGTH')==3 and get('STATUS')==0
    capture('初始画面',2200)
    press('START');assert get('STATUS')==1
    capture('按下 START',1500)
    for i in range(4):
        press('STEP')
        if i==3:
            assert get('SCORE')==1 and get('LENGTH')==4
            capture('吃到食物，长度 +1',2500)
        else:capture('向右前进一步',650)
    press('UP','STEP');capture('按 UP，向上转弯',1000)
    press('STEP');capture('继续向上',700)
    if not obstacle_mode:
        press('LEFT','STEP');capture('按 LEFT，向左转弯',1000)
        press('STEP');capture('继续向左',700)
    press('PAUSE');assert get('STATUS')==2
    before=get('FRAME');run(1000);assert get('FRAME')==before
    capture('按 PAUSE，游戏暂停',2400)
    press('PAUSE');assert get('STATUS')==1
    capture('再次按 PAUSE，恢复',1300)
    if obstacle_mode:
        press('STEP');capture('沿通道向上前进',1000)
    else:
        press('UP','STEP');capture('向上接近边界',600)
        for _ in range(5):press('STEP');capture('继续向上',450)
    press('STEP');assert get('STATUS')==3
    assert get('CAUSE')==(3 if obstacle_mode else 1)
    capture('撞到障碍物，游戏结束' if obstacle_mode else '撞到边界，游戏结束',2400)
    press('RESTART')
    assert get('STATUS')==0 and get('SCORE')==0 and get('BEST')==1
    capture('按 RESTART，保留最高分',2600)
    basename='snake-obstacles-demo' if obstacle_mode else 'snake-demo'
    out=ROOT/f'build/{basename}.gif'
    frames[0].save(out,save_all=True,append_images=frames[1:],duration=durations,loop=0,optimize=True,disposal=2)
    frames[5].save(ROOT/f'build/{basename}-poster.png')
    record_name='obstacles-demo-record.json' if obstacle_mode else 'demo-record.json'
    (ROOT/f'build/{record_name}').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print('DEMO COMPLETE',out,'frames',len(frames),'duration_ms',sum(durations),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--obstacles',action='store_true');args=parser.parse_args()
    J=start();code=0
    try:demonstrate(J,args.obstacles)
    except BaseException:
        import traceback;traceback.print_exc();code=1
    finally:finish(J,code)
