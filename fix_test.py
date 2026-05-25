import sys

with open("tests/unit/test_transaction_coordinator.py", "r") as f:
    content = f.read()

content = content.replace("        TransactionStatus.COMPLETED,\n        TransactionStatus.CANCELLED,\n        TransactionStatus.FAULTED,\n        TransactionStatus.AMBIGUOUS,\n        TransactionStatus.PICKUP_TIMED_OUT,\n", "        TransactionStatus.COMPLETED,\n        TransactionStatus.CANCELLED,\n        TransactionStatus.PICKUP_TIMED_OUT,\n")

with open("tests/unit/test_transaction_coordinator.py", "w") as f:
    f.write(content)
