from karst.ast_engine import *
from karst.basic import *


def test_if_transform():
    model = define_fifo(42)
    model.Variable("a", 1, 0)
    model.Variable("b", 1, 0)

    def _test_if():
        if model.a == 0:
            model.a = 1
        else:
            model.b = 1

    txt = textwrap.dedent(inspect.getsource(_test_if))


def test_assign_transform():
    class TestClass:
        def __init__(self):
            self.value = 0

        def __call__(self, *args, **kwargs):
            self.value = args[0]

    test = TestClass()

    def _test_assign():
        test = 2

    txt = textwrap.dedent(inspect.getsource(_test_assign))
    tree = ast.parse(txt)
    AssignNodeVisitor.visit(tree)
    ast.fix_missing_locations(tree)
