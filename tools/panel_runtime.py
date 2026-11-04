"""Helpers for inspecting the real RGB display, not a second game engine."""
from PIL import Image, ImageDraw


def display_pixels(state, circuit):
    result={}
    for c in circuit.getNonWires():
        if str(c.getFactory().getName())!='Snake RGB Display':continue
        values=[]
        for end in c.getEnds():
            v=state.getValue(end.getLocation())
            if not v.isFullyDefined():raise AssertionError(f'RGB bus={v}')
            values.append(int(v.toIntValue()))
        for row in range(16):
            for col in range(16):
                value=(values[row*2+col//8] >> ((col%8)*3)) & 7
                result[(row,col)]=tuple((value>>bit)&1 for bit in range(3))
    assert len(result)==256
    return result


def pixel_board(state,circuit,size=640):
    """A square visualization of the exact RGB bus values in the native display."""
    pixels=display_pixels(state,circuit)
    board=Image.new('RGB',(size,size),'#152a31')
    draw=ImageDraw.Draw(board);cell=size//16
    for (row,col),(r,g,b) in pixels.items():
        if r or g or b:
            color=(240 if r else 0,210 if g else 0,230 if b else 0)
            draw.rectangle((col*cell+1,row*cell+1,(col+1)*cell-2,(row+1)*cell-2),fill=color)
        else:
            draw.rectangle((col*cell,row*cell,(col+1)*cell-1,(row+1)*cell-1),outline='#1c343b')
    return board
