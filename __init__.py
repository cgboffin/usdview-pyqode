from six import exec_
import sys
import os
import functools
from code import InteractiveConsole

os.environ["QT_API"] = "pyside"
from pyqode.core.backend import server
from pyqode.python.widgets.code_edit import PyCodeEdit
from pyqode.qt import QtWidgets, QtCore

from pxr import Tf
from pxr.Usdviewq import plugin

_BASE_MENU_NAME = "Pyqode Script Editor"


class Interpreter(InteractiveConsole):
    def __init__(self, usdviewApi, local_vars=None):
        InteractiveConsole.__init__(self, local_vars)
        # Inject the UsdviewApi into the interpreter variables.
        interpreter_locals = vars()
        interpreter_locals["usdviewApi"] = usdviewApi

        self.auto_imports()

        # Run $PYTHONSTARTUP startup script.
        startup_file = os.getenv("PYTHONSTARTUP")
        if startup_file:
            path = os.path.realpath(os.path.expanduser(startup_file))
            if os.path.isfile(path):
                self.exec_startup(path)
        self.locals.update(interpreter_locals)

    def auto_imports(self):
        modules = Tf.ScriptModuleLoader().GetModulesDict()
        for name, mod in modules.items():
            self.runsource("import " + mod.__name__ + " as " + name + "\n")

    def exec_startup(self, path):
        self.runsource(
            'g = dict(globals()); g["__file__"] = '
            + '"%s"; execfile("%s", g);' % (path, path)
            + 'del g["__file__"]; globals().update(g);'
        )


class UsdviewPyCodeEdit(PyCodeEdit):
    def __init__(
        self,
        usdviewApi,
        parent=None,
        server_script=server.__file__,
        interpreter=sys.executable,
        args=None,
        create_default_actions=True,
        color_scheme="qt",
        reuse_backend=False,
    ):
        super(UsdviewPyCodeEdit, self).__init__(
            parent=parent,
            server_script=server_script,
            interpreter=interpreter,
            args=args,
            create_default_actions=create_default_actions,
            color_scheme=color_scheme,
            reuse_backend=reuse_backend,
        )
        # start the backend as soon as possible
        self._interpreter = Interpreter(usdviewApi)
        self.backend.stop()
        self.backend.start(
            self.backend.server_script,
            interpreter=interpreter, args=self.backend.args)
        # self.modes.remove("CodeCompletionMode")  # disabled for now due to problems

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Enter,):
            selected_text = self.textCursor().selection().toPlainText()
            document_text = self.document().toPlainText()
            execute_text = selected_text if selected_text else document_text
            for line in execute_text.splitlines():
                self._interpreter.push(line)
            event.accept()
            return
        if event.modifiers() == QtCore.Qt.ControlModifier and event.key() in (
            QtCore.Qt.Key_Return,
        ):
            selected_text = self.textCursor().selection().toPlainText()
            document_text = self.document().toPlainText()
            execute_text = selected_text if selected_text else document_text
            code_text = execute_text.encode("ascii", "replace")
            self.compile_code(code_text)
            event.accept()
            return
        super(UsdviewPyCodeEdit, self).keyPressEvent(event)

    def compile_code(self, text):
        compiled_code = compile(text, "<console>", "exec")
        exec_(compiled_code, globals(), self._interpreter.locals)


class PyqodeScriptEditorContainer(plugin.PluginContainer):
    def registerPlugins(self, _, __):
        self._interpreter_dialog = None
        self._interpreter = None

    def configureView(self, registry, builder):
        action = builder._mainWindow.menuBar().addAction(_BASE_MENU_NAME)
        action.triggered.connect(
            functools.partial(
                self._showInterpreter,
                registry._usdviewApi.qMainWindow,
                registry._usdviewApi,
            ),
        )

    def _showInterpreter(self, mainWindow, usdviewApi):

        if self._interpreter_dialog is None:
            self._interpreter_dialog = QtWidgets.QDialog(mainWindow)
            self._interpreter_dialog.setObjectName("Interpreter")

            self._console = UsdviewPyCodeEdit(
                usdviewApi, parent=self._interpreter_dialog, color_scheme="monokai"
            )
            self._console.show_whitespaces = True
            # change action shortcut
            self._console.action_duplicate_line.setShortcut("Ctrl+Shift+Down")
            self._interpreter_dialog.setFocusProxy(self._console)  # this is important!
            lay = QtWidgets.QVBoxLayout()
            lay.addWidget(self._console)
            self._interpreter_dialog.setLayout(lay)

        # dock the interpreter window next to the main usdview window
        self._interpreter_dialog.move(
            mainWindow.x() + mainWindow.frameGeometry().width(), mainWindow.y()
        )
        self._interpreter_dialog.resize(800, mainWindow.size().height() // 2)

        self._interpreter_dialog.show()
        self._interpreter_dialog.activateWindow()
        self._interpreter_dialog.setFocus()


Tf.Type.Define(PyqodeScriptEditorContainer)
