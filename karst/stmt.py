from karst.values import *


class If(Statement):
    def __init__(self, parent):
        super().__init__(parent)
        # an if must have predicate, expression, and else expression
        # else expression can be empty
        self.predicate: Expression = None
        self.expression: Expression = None
        self.else_expression: Expression = None
        # save the context
        self.context = parent.context[:]
        parent.context.clear()

    def __call__(self, predicate: Expression, expression: Expression):
        self.predicate = predicate
        self.expression = expression

    def else_(self, expression: Expression):
        self.else_expression = expression
        # restore the context since we branched off
        self.parent.context = self.context

    def eval(self):
        if self.predicate.eval():
            self.expression.eval()
        else:
            assert self.else_expression is not None
            self.else_expression.eval()

    def eq(self, other: "Statement"):
        if not isinstance(other, If):
            return False
        if (self.else_expression is None) ^ (other.else_expression is None):
            return False
        return self.predicate.eq(other.predicate) and \
            self.expression.eq(other.expression) and \
            (True if self.else_expression is None
             else self.else_expression.eq(other.else_expression))

    Else = else_


class ReturnStatement(Statement):
    def __init__(self, values: Union[List[Value], Value], parent):
        super().__init__(parent)
        if isinstance(values, Variable):
            values = [values]
        self.values = values

        self.parent = parent

    def eval(self):
        return [v.eval() for v in self.values]

    def eq(self, other: "Statement"):
        if not isinstance(other, ReturnStatement):
            return False
        return self.values == other.values
