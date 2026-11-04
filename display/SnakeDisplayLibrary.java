package snakeio;

import java.util.Arrays;
import java.util.List;
import com.cburch.logisim.tools.AddTool;
import com.cburch.logisim.tools.Library;
import com.cburch.logisim.tools.Tool;

public final class SnakeDisplayLibrary extends Library {
    private final List<Tool> tools=Arrays.<Tool>asList(new AddTool(new SnakeRgbDisplay()));
    @Override public String getName() { return "SnakeDisplay"; }
    @Override public List<? extends Tool> getTools() { return tools; }
}
