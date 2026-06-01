from manju.collector.keepawake import keep_awake


def test_keep_awake_is_a_safe_context_manager():
    # 비-Windows에선 no-op, Windows에선 절전 방지. 어느 쪽이든 예외 없이 진입/종료.
    with keep_awake() as k:
        assert k is not None
