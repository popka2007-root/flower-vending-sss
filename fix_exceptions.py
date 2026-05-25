import sys

with open("src/flower_vending/domain/exceptions/__init__.py", "r") as f:
    content = f.read()

content = content.replace("<<<<<<< Updated upstream\nclass TransactionRecoveryError(RecoveryError):\n    \"\"\"Raised when a restored active transaction is missing from the transaction set.\"\"\"\n=======\nclass TerminalLockedError(FlowerVendingError):\n    \"\"\"Raised when the terminal is locked due to a faulted or ambiguous transaction state.\"\"\"\n    def __init__(self, message: str = \"\") -> None:\n        super().__init__(\n            message,\n            user_message=\"Автомат временно заблокирован из-за технической ошибки. Пожалуйста, обратитесь к администратору.\",\n        )\n>>>>>>> Stashed changes",
"class TransactionRecoveryError(RecoveryError):\n    \"\"\"Raised when a restored active transaction is missing from the transaction set.\"\"\"\n\n\nclass TerminalLockedError(FlowerVendingError):\n    \"\"\"Raised when the terminal is locked due to a faulted or ambiguous transaction state.\"\"\"\n    def __init__(self, message: str = \"\") -> None:\n        super().__init__(\n            message,\n            user_message=\"Автомат временно заблокирован из-за технической ошибки. Пожалуйста, обратитесь к администратору.\",\n        )")

with open("src/flower_vending/domain/exceptions/__init__.py", "w") as f:
    f.write(content)
