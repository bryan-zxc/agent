class CodeSandbox:
    def __init__(self, globals_dict=None, locals_dict=None):
        if globals_dict:
            self.globals_dict = globals_dict
        else:
            self.globals_dict = {"__builtins__": __builtins__}
        self.locals_dict = locals_dict.copy() or {}

    def execute(self, code_string):
        try:
            # Create a StringIO to capture stdout
            import io
            import sys
            import traceback

            stdout_capture = io.StringIO()
            original_stdout = sys.stdout
            sys.stdout = stdout_capture

            # Execute the code with provided context
            exec(code_string, self.globals_dict, self.locals_dict)

            # Restore stdout and get the output
            sys.stdout = original_stdout
            output = stdout_capture.getvalue()

            return {"success": True, "output": output, "variables": self.locals_dict}
        except Exception as e:
            sys.stdout = original_stdout
            stack_trace = traceback.format_exc()
            return {"success": False, "error": str(e), "stack_trace": stack_trace}