import app.outputs.ndi as ndi_module


class FakeNdi:
    def __init__(self):
        self.initialize_calls = 0
        self.destroy_calls = 0

    def initialize(self):
        self.initialize_calls += 1
        return True

    def destroy(self):
        self.destroy_calls += 1


def test_disabled_ndi_does_not_initialize_native_runtime(monkeypatch):
    fake = FakeNdi()
    monkeypatch.setattr(ndi_module, "ndi", fake)
    monkeypatch.setattr(ndi_module, "NDI_AVAILABLE", True)

    output = ndi_module.NDIOutput(enabled=False)
    output.close()

    assert fake.initialize_calls == 0
    assert fake.destroy_calls == 0


def test_enabled_ndi_destroys_native_runtime_once(monkeypatch):
    fake = FakeNdi()
    monkeypatch.setattr(ndi_module, "ndi", fake)
    monkeypatch.setattr(ndi_module, "NDI_AVAILABLE", True)

    output = ndi_module.NDIOutput(enabled=True)
    output.close()

    assert fake.initialize_calls == 1
    assert fake.destroy_calls == 1
