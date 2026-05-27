ERROR_ALREADY_EXISTS = 183


def already_running(last_error: int) -> bool:
    return int(last_error) == ERROR_ALREADY_EXISTS


def notify_existing_instance(kernel32, event_name: str, event_modify_state: int) -> bool:
    event_handle = kernel32.OpenEventW(event_modify_state, False, event_name)
    if not event_handle:
        return False
    kernel32.SetEvent(event_handle)
    kernel32.CloseHandle(event_handle)
    return True
