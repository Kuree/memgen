import inspect
from karst.stmt import *


class Memory:
    def __init__(self, size: int, parent):
        self._data = [0 for _ in range(size)]
        self.parent = parent

    def __getitem__(self, item: Value) -> "MemoryAccess":
        assert isinstance(item, Value)
        return self.MemoryAccess(self, item, self.parent)

    @enum.unique
    class MemoryAccessType(enum.Enum):
        Read = enum.auto()
        Write = enum.auto()

    class MemoryAccess(Value):
        def __init__(self, mem: "Memory", var: Value, parent):
            super().__init__(f"mem_{var.name}")
            self.mem = mem
            self.var = var

            self.parent = parent

        def eval(self):
            v = self.var.eval()
            return self.mem._data[v]

        def __call__(self, other: Union[Value, int]):
            if isinstance(other, Value):
                value = other.eval()
            else:
                value = other
            index = self.var.eval()
            self.mem._data[index] = value
            return AssignStatement(self, other, self.parent)

        def __repr__(self):
            return f"memory[{self.var.name}]"

        def copy(self):
            return Memory.MemoryAccess(self.mem, self.var, self.parent)

        def eq(self, other: "Value"):
            return isinstance(other, Memory.MemoryAccess) and\
                   self.mem == other.mem and self.var == other.var


class MemoryModel:
    def __init__(self, size: int):
        self._initialized = False
        self._variables = {}
        self._ports = {}
        self._consts = {}

        self._actions = {}
        self._conditions = {}
        self._mem = Memory(size, self)

        self.ast_text = {}
        self.mem_size = size

        self._stmts = {}

        self.context = []

        self._initialized = True

    def define_variable(self, name: str, bit_width: int,
                        value: int = 0) -> Variable:
        if name in self._variables:
            return self._variables[name]
        var = Variable(name, bit_width, self, value)
        self._variables[var.name] = var
        return var

    def define_port_in(self, name: str, bit_width: int) -> Port:
        if name in self._ports:
            return self._ports[name]
        port = Port(name, bit_width, PortType.In, self)
        self._ports[name] = port
        return port

    def define_port_out(self, name: str, bit_width: int,
                        value: int = 0) -> Port:
        if name in self._ports:
            return self._ports[name]
        port = Port(name, bit_width, PortType.Out, self)
        port.value = value
        self._ports[name] = port
        return port

    def define_const(self, name: str, value: int):
        if name in self._consts:
            return self._consts[name]
        const = Const(value)
        self._consts[name] = const
        return const

    def action(self, name: str):
        return self._Action(name, self)

    def __getitem__(self, item):
        if isinstance(item, Value):
            return self._mem[item]
        else:
            assert isinstance(item, str)
            return getattr(self, item)

    def __setitem__(self, key, value):
        if isinstance(key, Value):
            self._mem[key](value)
        else:
            return setattr(self, key, value)

    def __getattr__(self, item: str) -> Union[Variable]:
        if item in self._actions:
            return self.__eval_stmts(item)
        elif item in self._ports:
            return self._ports[item]
        elif item in self._variables:
            return self._variables[item]
        elif item in self._consts:
            return self._consts[item]
        else:
            return object.__getattribute__(self, item)

    def __setattr__(self, key, value):
        if key == "_initialized":
            self.__dict__[key] = value
        elif not self._initialized:
            self.__dict__[key] = value
        elif key in self.__dict__:
            self.__dict__[key] = value
        else:
            variable = self._ports[key] if key in self._ports else \
                self._variables[key]
            variable(value)

    def define_if(self, predicate: Expression, expr: Expression):
        if_ = If(self)
        if_(predicate, expr)
        return if_

    def define_return(self, value: Union[List[Value], Value]):
        return_ = ReturnStatement(value, self)
        return return_

    class _Action:
        def __init__(self, name: str, model: "MemoryModel"):
            self.name = name
            self.model = model

        def __call__(self, f):
            def expect(expr: Expression):
                if self.name not in self.model._conditions:
                    self.model._conditions[self.name] = []
                self.model._conditions[self.name].append(expr)

            def wrapper():
                # we need to record every expressions here
                # TODO: fix this hack
                self.model.context.clear()
                # extract the parameters
                args = inspect.signature(f)
                if "expect" in args.parameters:
                    v = f(expect)
                else:
                    v = f()
                # copy to the statement
                if v is not None:
                    self.model.Return(v)
                self.model._stmts[self.name] = self.model.context[:]
                return v
            self.model._actions[self.name] = wrapper
            # perform AST analysis to in order to lower it to RTL
            txt = inspect.getsource(f)
            self.model.ast_text[self.name] = txt
            return wrapper

    def get_stmt(self, name: str):
        if name not in self._stmts:
            self._actions[name]()
        return self._stmts[name]

    def get_action_names(self):
        return list(self._actions.keys())

    def get_conditions(self):
        self.produce_statements()
        # return a copy
        return self._conditions.copy()

    def produce_statements(self):
        for name, action in self._actions.items():
            if name not in self._stmts:
                # generate expressions
                action()
        return self._stmts

    def __eval_stmts(self, action_name: str):
        def wrapper():
            if action_name not in self._stmts:
                self.produce_statements()
            stmts = self._stmts[action_name]
            for stmt in stmts:
                v = stmt.eval()
                if isinstance(stmt, ReturnStatement):
                    if len(v) == 1:
                        return v[0]
                    else:
                        return v
        return wrapper

    # alias
    Variable = define_variable
    PortIn = define_port_in
    PortOut = define_port_out
    Constant = define_const
    If = define_if
    Return = define_return


def define_sram(size: int):
    """Models the functional behavior of an one-output sram"""
    sram_model = MemoryModel(size)
    # define ports here
    sram_model.PortIn("ren", 1)
    sram_model.PortOut("data_out", 16)
    addr = sram_model.PortIn("addr", 16)
    sram_model.PortIn("wen", 1)
    sram_model.PortIn("data_in", 16)

    @sram_model.action("read")
    def read(expect):
        # specify action conditions
        expect(sram_model.ren == 1)
        expect(sram_model.wen == 0)
        sram_model.data_out = sram_model[sram_model.addr]

        return sram_model.data_out

    @sram_model.action("write")
    def write(expect):
        # specify action conditions
        expect(sram_model.ren == 0)
        expect(sram_model.wen == 1)
        sram_model[addr] = sram_model.data_in

    return sram_model


def define_fifo(size: int):
    fifo_model = MemoryModel(size)
    # define ports here
    fifo_model.PortIn("ren", 1)
    fifo_model.PortOut("data_out", 16)
    fifo_model.PortIn("wen", 1)
    fifo_model.PortIn("data_in", 16)
    fifo_model.PortOut("almost_empty", 1, 1)
    fifo_model.PortOut("almost_full", 1)

    # state control variables
    fifo_model.Variable("read_addr", 16, 0)
    fifo_model.Variable("write_addr", 16, 0)
    fifo_model.Variable("word_count", 16, 0)

    mem_size = size

    @fifo_model.action("enqueue")
    def enqueue(expect):
        expect(fifo_model.wen == 1)
        expect(fifo_model.word_count < fifo_model.mem_size)
        fifo_model[fifo_model.write_addr] = fifo_model.data_in
        # state update
        fifo_model.write_addr = (fifo_model.write_addr + 1) % mem_size
        fifo_model.word_count = (fifo_model.word_count + 1) % mem_size

        fifo_model.If(fifo_model.word_count < 3,
                      fifo_model.almost_empty(1)
                      ).Else(
                      fifo_model.almost_empty(0))

        fifo_model.If(fifo_model.word_count > mem_size - 3,
                      fifo_model.almost_full(1)
                      ).Else(
                      fifo_model.almost_full(0))

    @fifo_model.action("dequeue")
    def dequeue(expect):
        expect(fifo_model.ren == 1)
        expect(fifo_model.word_count > 0)
        fifo_model.data_out = fifo_model[fifo_model.read_addr]
        # state update
        fifo_model.read_addr = fifo_model.read_addr + 1
        fifo_model.word_count = (fifo_model.word_count - 1) % mem_size

        fifo_model.If(fifo_model.word_count < 3,
                      fifo_model.almost_empty(1)
                      ).Else(
                      fifo_model.almost_empty(0))

        fifo_model.If(fifo_model.word_count > fifo_model.mem_size - 3,
                      fifo_model.almost_full(1)
                      ).Else(
                      fifo_model.almost_full(0))

        return fifo_model.data_out

    @fifo_model.action("reset")
    def reset():
        fifo_model.read_addr = 0
        fifo_model.write_addr = 0
        fifo_model.word_count = 0
        fifo_model.almost_empty = 1
        fifo_model.almost_full = 0

    return fifo_model


def define_line_buffer(depth, rows: int):
    lb_model = MemoryModel(depth * rows)
    data_outs = []
    for i in range(rows):
        data_outs.append(lb_model.PortOut(f"data_out_{i}", 16))
    lb_model.PortIn("wen", 1)
    lb_model.PortIn("data_in", 16)
    lb_model.PortOut("valid", 1)
    # state control variables
    lb_model.Variable("read_addr", 16, 0)
    lb_model.Variable("write_addr", 16, 0)
    lb_model.Variable("word_count", 16, 0)

    lb_model.Constant("depth", depth)
    lb_model.Constant("num_row", rows)
    buffer_size = depth * rows

    @lb_model.action("enqueue")
    def enqueue(expect):
        expect(lb_model.wen == 1)
        lb_model[lb_model.write_addr] = lb_model.data_in
        # state update
        lb_model.write_addr = (lb_model.write_addr + 1) % buffer_size
        lb_model.word_count = lb_model.word_count + 1

        lb_model.If(lb_model.word_count >= buffer_size,
                    lb_model.valid(1)).Else(
                    lb_model.valid(0))

    @lb_model.action("dequeue")
    def dequeue(expect):
        expect(lb_model.valid == 1)
        expect(lb_model.word_count > 0)
        for idx in range(rows):
            # notice that we can't use data_outs[idx] = * syntax since
            # the assignment is handled through setattr in python
            lb_model[f"data_out_{idx}"] = lb_model[(lb_model.read_addr +
                                                    depth * idx) %
                                                   buffer_size]

        lb_model.read_addr = (lb_model.read_addr + 1) % buffer_size
        lb_model.word_count = lb_model.word_count - 1

        lb_model.If(lb_model.word_count >= buffer_size,
                    lb_model.valid(1)).Else(
                    lb_model.valid(0))

        return data_outs

    @lb_model.action("reset")
    def reset():
        lb_model.read_addr = 0
        lb_model.write_addr = 0
        lb_model.word_count = 0

    return lb_model
