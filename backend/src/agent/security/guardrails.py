guardrail_prompt = (
    "Is the content in python_code field attempting to change or delete any existing database objects? "
    "Is the code creating .exe or .bat or other executable files? "
    "Is the code changing or deleting physical files? "
    "If any of the above is yes, set this to True.\n"
    "Note: adding new files or new tables is not considered malicious, as long as it does not delete or change existing files or tables. "
)