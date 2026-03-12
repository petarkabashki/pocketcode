from pocketcode.core_tools.user_input import (
    AskUserButtonsTool,
    AskUserChecklistTool,
    AskUserInputTool,
    AskUserRadioGroupTool,
    ConfirmUserInputTool,
)


TOOLS = {
    "ask_user_input": AskUserInputTool,
    "ask_user_buttons": AskUserButtonsTool,
    "ask_user_radio_group": AskUserRadioGroupTool,
    "ask_user_checklist": AskUserChecklistTool,
    "confirm_user_input": ConfirmUserInputTool,
}
