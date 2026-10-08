"""Shared worker-local capabilities injected into Agent modules."""
class AgentServices:
    def __init__(self, *, cache=None, backend=None, data_api=None, extractor=None, input_observer=None):
        self.cache=cache; self.backend=backend; self.data_api=data_api
        self.extractor=extractor; self.input_observer=input_observer
