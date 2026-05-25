import sys

with open("src/flower_vending/app/orchestrators/transaction_coordinator.py", "r") as f:
    content = f.read()

content = content.replace("<<<<<<< Updated upstream\nfrom flower_vending.domain.exceptions import ConcurrencyConflictError, TransactionRecoveryError\n=======\nfrom flower_vending.domain.exceptions import ConcurrencyConflictError, TerminalLockedError\n>>>>>>> Stashed changes",
"from flower_vending.domain.exceptions import ConcurrencyConflictError, TerminalLockedError, TransactionRecoveryError")

content = content.replace("<<<<<<< Updated upstream\n    TransactionStatus.FAULTED,\n    TransactionStatus.AMBIGUOUS,\n    TransactionStatus.PICKUP_TIMED_OUT,\n=======\n    TransactionStatus.PICKUP_TIMED_OUT,\n    TransactionStatus.FAULTED,\n    TransactionStatus.AMBIGUOUS,\n>>>>>>> Stashed changes",
"    TransactionStatus.PICKUP_TIMED_OUT,\n    TransactionStatus.FAULTED,\n    TransactionStatus.AMBIGUOUS,")

with open("src/flower_vending/app/orchestrators/transaction_coordinator.py", "w") as f:
    f.write(content)
