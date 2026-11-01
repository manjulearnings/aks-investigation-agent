from aks_agent.parser import AKSLogParser


def test_parse_crio_format():
    parser = AKSLogParser()
    raw = (
        "2026-11-01T10:00:00.123456Z stdout F [INFO] Server started\n"
        "2026-11-01T10:00:01.123456Z stderr F [ERROR] Failed to allocate IP address from subnet\n"
    )
    entries = parser.parse_text(raw)
    assert len(entries) == 2
    assert entries[0].stream == "stdout"
    assert entries[1].stream == "stderr"
    assert entries[1].log_level == "ERROR"
    assert "allocate IP address" in entries[1].message


def test_parse_azure_containerlogv2_json():
    parser = AKSLogParser()
    raw = (
        '{"TimeGenerated": "2026-11-01T12:00:00Z", "PodName": "cart-6b78-98ks", "LogMessage": "Out of memory", "LogLevel": "Error", "Computer": "aks-nodepool1-vmss000001"}\n'
    )
    entries = parser.parse_text(raw)
    assert len(entries) == 1
    assert entries[0].pod_name == "cart-6b78-98ks"
    assert entries[0].azure_properties.get("Computer") == "aks-nodepool1-vmss000001"
    assert entries[0].log_level == "ERROR"


def test_parse_multiline_stack_trace():
    parser = AKSLogParser()
    raw = (
        "2026-11-01T10:00:00Z stderr F Traceback (most recent call last):\n"
        "2026-11-01T10:00:00Z stderr F   File 'app.py', line 42, in process\n"
        "2026-11-01T10:00:00Z stderr F ZeroDivisionError: division by zero\n"
    )
    entries = parser.parse_text(raw)
    assert len(entries) == 1
    assert entries[0].is_stack_trace is True
    assert "ZeroDivisionError" in entries[0].message

