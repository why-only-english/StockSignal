"""An explicitly missing latest close can be retried at a later scheduled slot."""
class DataPending(ValueError):
    pass
