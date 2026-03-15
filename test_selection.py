import textual.widgets
print([attr for attr in dir(textual.widgets.Static) if "select" in attr.lower() or "text" in attr.lower() or "markup" in attr.lower()])
