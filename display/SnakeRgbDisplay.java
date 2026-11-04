package snakeio;

import java.awt.Color;
import java.awt.Font;
import java.awt.Graphics;
import com.cburch.logisim.data.Attribute;
import com.cburch.logisim.data.Bounds;
import com.cburch.logisim.data.Value;
import com.cburch.logisim.instance.InstanceFactory;
import com.cburch.logisim.instance.InstancePainter;
import com.cburch.logisim.instance.InstanceState;
import com.cburch.logisim.instance.Port;

/** Stateless output peripheral. Every pixel comes directly from circuit inputs. */
public final class SnakeRgbDisplay extends InstanceFactory {
    private static final Color[] COLORS = {
        new Color(21,42,49), new Color(240,75,85), new Color(45,210,125),
        new Color(240,205,75), new Color(65,110,235), new Color(220,95,220),
        new Color(55,220,235), Color.WHITE
    };

    public SnakeRgbDisplay() {
        super("Snake RGB Display");
        setAttributes(new Attribute[0], new Object[0]);
        setOffsetBounds(Bounds.create(0,-40,390,370));
        Port[] ports = new Port[32];
        for (int i=0;i<32;i++) ports[i]=new Port(0,i*10,Port.INPUT,24);
        setPorts(ports);
    }

    @Override public void propagate(InstanceState state) {
        // No clock, storage, or game behavior lives in this display component.
    }

    @Override public void paintInstance(InstancePainter painter) {
        Graphics g=painter.getGraphics();
        int x=painter.getLocation().getX(), y=painter.getLocation().getY();
        g.setColor(new Color(15,28,42));g.fillRoundRect(x+35,y-35,345,365,12,12);
        g.setColor(new Color(220,235,245));g.setFont(new Font("SansSerif",Font.BOLD,13));
        g.drawString("16 x 16 RGB DISPLAY",x+50,y-15);
        for (int row=0;row<16;row++) {
            for (int col=0;col<16;col++) {
                Value value=painter.getPort(row*2+col/8);
                int color=value.isFullyDefined() ? (value.toIntValue() >>> ((col%8)*3)) & 7 : 0;
                g.setColor(COLORS[color]);
                g.fillRect(x+50+col*20,y+row*20,19,19);
            }
        }
        painter.drawPorts();
    }
}
