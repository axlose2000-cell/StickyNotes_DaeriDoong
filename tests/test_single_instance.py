import unittest

from instance_control import already_running, notify_existing_instance


class _FakeKernel32:
    def __init__(self, handle=1):
        self.handle = handle
        self.set_called = False
        self.closed = False

    def OpenEventW(self, _access, _inherit, _name):
        return self.handle

    def SetEvent(self, _handle):
        self.set_called = True

    def CloseHandle(self, _handle):
        self.closed = True


class SingleInstanceTests(unittest.TestCase):
    def test_already_running_detection(self):
        self.assertTrue(already_running(183))
        self.assertFalse(already_running(0))

    def test_notify_existing_instance(self):
        k = _FakeKernel32(handle=10)
        ok = notify_existing_instance(k, "Local\\StickyNotesAppActivateEventV1", 0x0002)
        self.assertTrue(ok)
        self.assertTrue(k.set_called)
        self.assertTrue(k.closed)


if __name__ == "__main__":
    unittest.main()
